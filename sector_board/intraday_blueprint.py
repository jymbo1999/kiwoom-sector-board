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
_MAX_WEBSOCKET_CODES = 200          # Kiwoom WebSocket 세션 총 등록 상한
_DEFAULT_SNAPSHOT_INTERVAL = 1.0
_DEFAULT_MAX_CODES = 150
_DEFAULT_LISTEN_SECONDS = 7200      # 2시간


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
        layout = current_app.config.get(
            "SECTOR_BOARD_LAYOUT_TEMPLATE", "sector_board/standalone.html"
        )
        runtime = _get_runtime()
        runtime_state = runtime.get_status()["state"] if runtime else "not_running"
        return render_template(
            "sector_board/intraday_live.html",
            layout_template=layout,
            runtime_state=runtime_state,
        )

    # ------------------------------------------------------------------ #
    # GET /intraday/api/snapshot                                          #
    # ------------------------------------------------------------------ #

    @blueprint.route("/api/snapshot")
    def api_snapshot():
        """최신 snapshot + 런타임 진단 정보를 JSON 으로 반환한다.

        런타임이 없으면 status="not_running", snapshot 없으면 status="empty".
        항상 200 OK 를 반환하고 클라이언트가 status/ok 로 판단한다.
        """
        runtime = _get_runtime()

        if runtime is None:
            return jsonify({
                "ok": False,
                "status": "not_running",
                "running": False,
                "runtime_state": "not_running",
                "started_at": None,
                "updated_at": None,
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

        base = {
            "running": rt["state"] == "running",
            "runtime_state": rt["state"],
            "runtime_error": rt.get("error"),
            "runtime_close_reason": rt.get("close_reason"),
            "started_at": rt.get("started_at"),
        }

        if snap is None:
            return jsonify({
                "ok": False,
                "status": "empty",
                "updated_at": None,
                "latest_count": 0,
                "bucket_count": 0,
                "raw_row_count": 0,
                "ignored_row_count": 0,
                "sector_count": 0,
                "sector_views": [],
                **base,
            }), 200

        return jsonify({
            **snap,                                  # status, minute_key, counts, sector_views …
            **base,
            "ok": True,
            "updated_at": snap.get("generated_at"),
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
            return jsonify({"ok": True, "message": "already running"}), 200

        body: dict = {}
        try:
            body = request.get_json(silent=True) or {}
        except Exception:
            pass

        provider = str(body.get("provider") or "mock").lower()
        exchange = str(body.get("exchange") or "sor").lower()
        snapshot_interval = float(body.get("snapshot_interval") or _DEFAULT_SNAPSHOT_INTERVAL)
        max_codes = int(body.get("max_codes") or _DEFAULT_MAX_CODES)
        max_total_realtime_codes = int(
            body.get("max_total_realtime_codes") or _MAX_WEBSOCKET_CODES
        )
        listen_seconds = float(body.get("listen_seconds") or _DEFAULT_LISTEN_SECONDS)

        project_root = Path(__file__).resolve().parent.parent
        codes_file = Path(
            body.get("codes_file") or project_root / "data" / "universe_codes_150.txt"
        )
        sector_map_file = Path(
            body.get("sector_map_file") or project_root / "data" / "sector_map.json"
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
            source_factory = make_mock_source(base_codes, exchange)
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

            kiwoom_env = str(body.get("kiwoom_env") or "prod").lower()
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

        else:
            return jsonify({
                "ok": False,
                "error": (
                    f"지원하지 않는 provider: {provider!r}. "
                    "가능한 값: 'mock', 'websocket'"
                ),
            }), 400

        # ---- Service + Runtime 생성 ----
        from src.intraday_snapshot_service import IntradaySnapshotService
        from src.intraday_runtime import IntradayRuntime

        service = IntradaySnapshotService(
            sector_map=sector_map,
            sector_limit=5,
            stock_limit=5,
        )
        runtime = IntradayRuntime(
            service=service,
            message_source_factory=source_factory,
            snapshot_interval=snapshot_interval,
        )
        runtime.start()
        _set_runtime(runtime)

        return jsonify({
            "ok": True,
            "provider": provider,
            "exchange": exchange,
            "codes": len(base_codes),
            "sector_map_size": len(sector_map),
            "snapshot_interval": snapshot_interval,
            "max_total_realtime_codes": max_total_realtime_codes,
            **response_extra,
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

    return blueprint


# ---------------------------------------------------------------------------
# Runtime 저장 헬퍼 (Flask app.config 사용 → 테스트 격리 보장)
# ---------------------------------------------------------------------------


def _get_runtime():
    return current_app.config.get(_RUNTIME_KEY)


def _set_runtime(rt) -> None:
    current_app.config[_RUNTIME_KEY] = rt


# ---------------------------------------------------------------------------
# 파일 로드 헬퍼
# ---------------------------------------------------------------------------


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
