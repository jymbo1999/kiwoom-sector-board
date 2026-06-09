"""장중 리더보드 Flask Blueprint.

routes:
  GET  /intraday/               HTML 대시보드 (1초 polling)
  GET  /intraday/api/snapshot   최신 snapshot + 진단 JSON
  POST /intraday/api/start      runtime 시작 (mock 또는 websocket)
  POST /intraday/api/stop       runtime 중지

runtime 은 Flask app.config["INTRADAY_RUNTIME"] 에 저장한다.
화면 접속만으로 WebSocket 이 자동 시작되지 않는다.
POST /intraday/api/start 로 명시적으로 시작해야 한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request

from .auth import auth_gate

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

_RUNTIME_KEY = "INTRADAY_RUNTIME"
_RUNTIME_META_KEY = "INTRADAY_RUNTIME_META"
_MAX_WEBSOCKET_CODES = 200          # Kiwoom WebSocket 세션 총 등록 상한
_DEFAULT_SNAPSHOT_INTERVAL = 1.0
_DEFAULT_MAX_CODES = 200
_DEFAULT_LISTEN_SECONDS = 28800     # 8시간 (장 전체 커버)
_SENSITIVE_ENV_PARTS = ("SECRET", "APP_KEY", "TOKEN", "PASSWORD")


# ---------------------------------------------------------------------------
# Blueprint 팩토리
# ---------------------------------------------------------------------------


def create_intraday_blueprint() -> Blueprint:
    blueprint = Blueprint(
        "intraday",
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    @blueprint.before_request
    def require_auth():
        return auth_gate()

    # ------------------------------------------------------------------ #
    # GET /intraday/                                                       #
    # ------------------------------------------------------------------ #

    @blueprint.route("/", strict_slashes=False)
    def index():
        """장중 리더보드 HTML (1초 polling 기반)."""
        runtime = _get_runtime()
        runtime_state = runtime.get_status()["state"] if runtime else "not_running"
        return render_template(
            "sector_board/intraday_live.html",
            layout_template="sector_board/standalone.html",
            runtime_state=runtime_state,
        )

    # ------------------------------------------------------------------ #
    # GET /intraday/api/snapshot                                          #
    # ------------------------------------------------------------------ #

    @blueprint.route("/api/snapshot")
    def api_snapshot():
        """최신 snapshot + 런타임 진단 정보를 JSON 으로 반환한다.

        런타임이 없으면 status="not_running", 실행 중 snapshot 없으면 status="warming".
        항상 200 OK 를 반환하고 클라이언트가 status/ok 로 판단한다.
        """
        runtime = _get_runtime()

        if runtime is None:
            return jsonify({
                "ok": False,
                "status": "not_running",
                "provider": None,
                "exchange": None,
                "running": False,
                "runtime_state": "not_running",
                "started_at": None,
                "updated_at": None,
                "last_updated_at": None,
                "runtime_error": None,
                "runtime_close_reason": None,
                "latest_count": 0,
                "bucket_count": 0,
                "raw_row_count": 0,
                "ignored_row_count": 0,
                "sector_count": 0,
                "sector_views": [],
            }), 200

        snap = runtime.get_latest_snapshot()
        rt = runtime.get_status()
        meta = _get_runtime_meta()
        runtime_error = _redact_sensitive_text(rt.get("error"))
        runtime_close_reason = _redact_sensitive_text(rt.get("close_reason"))
        running = rt["state"] == "running"
        raw_debug = rt.get("close_debug")
        runtime_close_debug = (
            {**raw_debug, "raw_cause": _redact_sensitive_text(raw_debug.get("raw_cause"))}
            if raw_debug else None
        )

        base = {
            **meta,
            "running": running,
            "runtime_state": rt["state"],
            "runtime_error": runtime_error,
            "runtime_close_reason": runtime_close_reason,
            "runtime_close_debug": runtime_close_debug,
            "started_at": rt.get("started_at"),
        }

        if snap is None:
            status = "error" if runtime_error else ("warming" if running else "not_running")
            return jsonify({
                "ok": False,
                "status": status,
                "updated_at": None,
                "last_updated_at": None,
                "latest_count": 0,
                "bucket_count": 0,
                "raw_row_count": 0,
                "ignored_row_count": 0,
                "sector_count": 0,
                "sector_views": [],
                "rule": _build_rule_info(meta),
                **base,
            }), 200

        status = "error" if runtime_error else snap.get("status", "empty")
        if status == "empty" and running:
            status = "warming"
        updated_at = snap.get("generated_at")
        rule = _build_rule_info(_get_runtime_meta())
        return jsonify({
            **snap,                                  # status, minute_key, counts, sector_views …
            **base,
            "ok": runtime_error is None,
            "status": status,
            "updated_at": updated_at,
            "last_updated_at": updated_at,
            "rule": rule,
        }), 200

    # ------------------------------------------------------------------ #
    # POST /intraday/api/start                                            #
    # ------------------------------------------------------------------ #

    @blueprint.route("/api/start", methods=["POST"])
    def api_start():
        """runtime 을 시작한다.

        JSON body (모두 선택적):
            provider:                "mock" (기본) | "websocket"
            kiwoom_env:              "prod" | "real" | "mock"  (websocket 전용, 기본 "prod")
            exchange:                "sor" (기본) | "nxt" | "krx"
            codes_file:              universe 코드 파일 경로
            sector_map_file:         sector_map JSON 경로
            max_codes:               최대 종목 수 (기본 150)
            max_total_realtime_codes: WebSocket 세션 상한 (기본 200)
            snapshot_interval:       초 단위 float (기본 1.0)
            listen_seconds:          WebSocket 수신 시간(초) (기본 7200, websocket 전용)
        """
        existing = _get_runtime()
        if existing and existing.is_running():
            return jsonify({
                "ok": True,
                "message": "already running",
                **_get_runtime_meta(),
            }), 200

        body: dict = {}
        try:
            body = request.get_json(silent=True) or {}
        except Exception:
            pass

        provider = str(_body_value(body, "provider") or "mock").lower()
        exchange = str(_body_value(body, "exchange") or "sor").lower()
        if provider not in {"mock", "websocket"}:
            return jsonify({
                "ok": False,
                "error": (
                    f"지원하지 않는 provider: {provider!r}. "
                    "가능한 값: 'mock', 'websocket'"
                ),
            }), 400

        _si = body.get("snapshot_interval")
        snapshot_interval = float(_si) if _si is not None else _DEFAULT_SNAPSHOT_INTERVAL
        _mc = body.get("max_codes")
        max_codes = int(_mc) if _mc is not None else _DEFAULT_MAX_CODES
        _mtr = body.get("max_total_realtime_codes")
        max_total_realtime_codes = int(_mtr) if _mtr is not None else _MAX_WEBSOCKET_CODES
        _ls = body.get("listen_seconds")
        listen_seconds = float(_ls) if _ls is not None else _DEFAULT_LISTEN_SECONDS

        project_root = Path(__file__).resolve().parent.parent
        data_dir = _default_data_dir(project_root)
        codes_file = _resolve_data_file(
            _body_value(body, "codes_file", "codes-file", "codesFile"),
            data_dir / "universe_codes_200.txt",
            project_root,
        )
        sector_map_file = _resolve_data_file(
            _body_value(body, "sector_map_file", "sector-map-file", "sectorMapFile"),
            data_dir / "sector_map.json",
            project_root,
        )

        # ---- 파일 로드 ----
        sector_map = _load_sector_map(sector_map_file)
        raw_codes = _load_codes(codes_file)
        base_codes = raw_codes[:max_codes] if max_codes > 0 else raw_codes

        if not base_codes:
            return jsonify({
                "ok": False,
                "error": f"종목코드를 로드할 수 없습니다. 파일을 확인하세요: {codes_file}",
            }), 400

        # ---- Provider 별 처리 ----
        if provider == "mock":
            from src.intraday_runtime import make_mock_source
            source_factory = make_mock_source(base_codes, exchange, sector_map=sector_map)
            kiwoom_env = None
            response_extra: dict = {}

        elif provider == "websocket":
            # 200종목 제한 체크 (sor/nxt/krx 는 base_codes 와 1:1 매핑)
            formatted_code_count = len(base_codes)
            if formatted_code_count > max_total_realtime_codes:
                return jsonify({
                    "ok": False,
                    "error": (
                        f"formatted_code_count={formatted_code_count} > "
                        f"max_total_realtime_codes={max_total_realtime_codes}. "
                        f"Kiwoom WebSocket 실시간 등록 상한은 세션당 {_MAX_WEBSOCKET_CODES}종목입니다. "
                        f"max_codes 를 {max_total_realtime_codes} 이하로 줄이세요."
                    ),
                    "formatted_code_count": formatted_code_count,
                    "max_total_realtime_codes": max_total_realtime_codes,
                }), 400

            kiwoom_env = str(_body_value(body, "kiwoom_env", "kiwoom-env") or "prod").lower()
            os.environ["KIWOOM_ENV"] = kiwoom_env

            from src.intraday_runtime import make_websocket_source
            source_factory = make_websocket_source(
                base_codes=base_codes,
                exchange=exchange,
                listen_seconds=listen_seconds,
            )
            response_extra = {
                "kiwoom_env": kiwoom_env,
                "listen_seconds": listen_seconds,
                "formatted_code_count": formatted_code_count,
            }

        # ---- Service + Runtime 생성 ----
        from src.intraday_snapshot_service import IntradaySnapshotService
        from src.intraday_runtime import IntradayRuntime

        market_cap_map = _load_market_cap_map(data_dir)
        service = IntradaySnapshotService(
            sector_map=sector_map,
            sector_limit=30,
            stock_limit=20,
            name_map=_load_name_map(data_dir),
            market_cap_map=market_cap_map,
            min_riser_count=2,
        )
        runtime = IntradayRuntime(
            service=service,
            message_source_factory=source_factory,
            snapshot_interval=snapshot_interval,
        )
        runtime.start()
        metadata = {
            "provider": provider,
            "exchange": exchange,
            "kiwoom_env": kiwoom_env,
            "codes": len(base_codes),
            "sector_map_size": len(sector_map),
            "codes_file": _display_path(codes_file, project_root, data_dir),
            "sector_map_file": _display_path(sector_map_file, project_root, data_dir),
            "snapshot_interval": snapshot_interval,
            "max_total_realtime_codes": max_total_realtime_codes,
            "market_cap_filter_enabled": bool(market_cap_map),
            **response_extra,
        }
        _set_runtime(runtime, metadata)

        return jsonify({
            "ok": True,
            **metadata,
        }), 200

    # ------------------------------------------------------------------ #
    # POST /intraday/api/stop                                             #
    # ------------------------------------------------------------------ #

    @blueprint.route("/api/stop", methods=["POST"])
    def api_stop():
        """runtime 을 중지한다."""
        runtime = _get_runtime()
        if runtime is None:
            return jsonify({"ok": True, "message": "not running"}), 200

        runtime.stop(timeout=5.0)
        _set_runtime(None)
        return jsonify({"ok": True, "message": "stopped"}), 200

    @blueprint.route("/api/outbound-ip")
    def api_outbound_ip():
        """서버의 공인 IP 주소를 반환한다 (키움 IP 등록 안내용)."""
        import urllib.request
        import urllib.error
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
                ip = resp.read(64).decode("utf-8").strip()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, "ip": ip}), 200

    return blueprint


# ---------------------------------------------------------------------------
# Runtime 저장 헬퍼 (Flask app.config 사용 → 테스트 격리 보장)
# ---------------------------------------------------------------------------


def _get_runtime():
    return current_app.config.get(_RUNTIME_KEY)


def _set_runtime(rt, metadata: dict | None = None) -> None:
    current_app.config[_RUNTIME_KEY] = rt
    current_app.config[_RUNTIME_META_KEY] = metadata or {}


def _get_runtime_meta() -> dict:
    meta = current_app.config.get(_RUNTIME_META_KEY) or {}
    return {
        "provider": meta.get("provider"),
        "exchange": meta.get("exchange"),
        "kiwoom_env": meta.get("kiwoom_env"),
        "codes": meta.get("codes", 0),
        "sector_map_size": meta.get("sector_map_size", 0),
        "codes_file": meta.get("codes_file"),
        "sector_map_file": meta.get("sector_map_file"),
        "snapshot_interval": meta.get("snapshot_interval"),
        "max_total_realtime_codes": meta.get("max_total_realtime_codes"),
        "market_cap_filter_enabled": meta.get("market_cap_filter_enabled", False),
    }


def _build_rule_info(meta: dict) -> dict:
    """현재 적용 중인 v4 룰 정보를 반환한다."""
    enabled = meta.get("market_cap_filter_enabled", False)
    rule: dict = {
        "version": "v4",
        "market_cap_filter_enabled": enabled,
        "min_market_cap": 500_000_000_000 if enabled else None,
        "riser_threshold": 5.0,
        "min_riser_count": 2,
        "strong_threshold": 10.0,
        "uses_7_percent_threshold": False,
    }
    if not enabled:
        rule["warning"] = "market_cap_map.json missing. Market cap filter is disabled."
    return rule


# ---------------------------------------------------------------------------
# 파일 로드 헬퍼
# ---------------------------------------------------------------------------


def _load_market_cap_map(data_dir: Path) -> dict[str, int]:
    """market_cap_map.json 을 로드한다. 파일 없으면 빈 dict."""
    path = data_dir / "market_cap_map.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                str(k).zfill(6): int(v)
                for k, v in data.items()
                if isinstance(v, (int, float)) and v > 0
            }
    except Exception:
        pass
    return {}


def _load_sector_map(path: Path) -> dict[str, list[str]]:
    """sector_map.json 을 로드한다. 파일 없으면 빈 dict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                str(k).zfill(6): v
                for k, v in data.items()
                if isinstance(v, list)
            }
    except Exception:
        pass
    return {}


def _load_name_map(data_dir: Path) -> dict[str, str]:
    """code → name 매핑을 로드한다.

    우선순위:
      1. name_map.json  (KRX 전체 목록 기반, 가장 완전함)
      2. theme_map.csv  (fallback)
    """
    result: dict[str, str] = {}

    # 1. theme_map.csv (fallback)
    csv_path = data_dir / "theme_map.csv"
    try:
        import csv as _csv
        with csv_path.open(encoding="utf-8", newline="") as f:
            for row in _csv.DictReader(f):
                code = str(row.get("code", "")).strip().zfill(6)
                name = str(row.get("name", "")).strip()
                if code and name:
                    result[code] = name
    except Exception:
        pass

    # 2. name_map.json 로 덮어쓰기 (더 완전한 소스)
    json_path = data_dir / "name_map.json"
    try:
        import json as _json
        data = _json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                code = str(k).strip().zfill(6)
                name = str(v).strip()
                if code and name:
                    result[code] = name
    except Exception:
        pass

    return result


def _load_codes(path: Path) -> list[str]:
    """universe 코드 파일을 로드한다. 파일 없으면 빈 리스트."""
    try:
        codes = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and s.isdigit() and len(s) <= 6:
                codes.append(s.zfill(6))
        return codes
    except Exception:
        return []


def _body_value(body: dict, *names: str):
    for name in names:
        if name in body:
            return body.get(name)
    return None


def _resolve_data_file(value, default_path: Path, project_root: Path) -> Path:
    if value is None or str(value).strip() == "":
        return default_path
    path = Path(str(value))
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return default_path.parent.joinpath(*path.parts[1:])
    return project_root / path


def _default_data_dir(project_root: Path) -> Path:
    try:
        from src.config import DATA_DIR

        return DATA_DIR
    except Exception:
        return project_root / "data"


def _display_path(path: Path, project_root: Path, data_dir: Path | None = None) -> str:
    if data_dir is not None:
        try:
            return "data/" + str(path.resolve().relative_to(data_dir.resolve()))
        except ValueError:
            pass
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path)


def _redact_sensitive_text(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    for key, raw in os.environ.items():
        if not raw or len(raw) < 4:
            continue
        if any(part in key.upper() for part in _SENSITIVE_ENV_PARTS):
            text = text.replace(raw, "[redacted]")
    return text
