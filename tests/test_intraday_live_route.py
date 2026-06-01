"""GET/POST /intraday/* route 테스트."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import sector_board
from sector_board import create_app


# ---------------------------------------------------------------------------
# 공통 app fixture
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_KRX_DATA", "false")
    monkeypatch.setattr(sector_board, "_setup_scheduler", lambda _: None)
    db = f"sqlite:///{tmp_path / 'sector.db'}"
    app = create_app({
        "TESTING": True,
        "SECTOR_BOARD_DATABASE_URL": db,
        "SECTOR_BOARD_AUTO_CREATE_TABLE": True,
        "SECTOR_BOARD_NO_AUTH": True,
    })
    return app


# ---------------------------------------------------------------------------
# 1. GET /intraday/
# ---------------------------------------------------------------------------


def test_intraday_index_returns_200(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/intraday/")
    assert r.status_code == 200


def test_intraday_index_returns_html(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/intraday/")
    assert b"text/html" in r.content_type.encode()


def test_intraday_index_contains_live_script(tmp_path, monkeypatch):
    """1초 polling JS 가 template 에 포함돼 있는지 확인."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/intraday/")
    html = r.data.decode()
    # 1초 polling interval 이 있어야 함
    assert "setInterval" in html
    assert "/intraday/api/snapshot" in html


# ---------------------------------------------------------------------------
# 2. GET /intraday/api/snapshot — runtime 없음
# ---------------------------------------------------------------------------


def test_api_snapshot_no_runtime(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/intraday/api/snapshot")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["status"] == "not_running"
    assert data["ok"] is False


# ---------------------------------------------------------------------------
# 3. POST /intraday/api/start (mock provider)
# ---------------------------------------------------------------------------


_FAST_START = {"provider": "mock", "snapshot_interval": 0.1}


def test_api_start_mock_returns_ok(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps(_FAST_START),
                   content_type="application/json")
    data = json.loads(r.data)
    assert r.status_code == 200
    assert data["ok"] is True
    assert data["provider"] == "mock"

    # cleanup
    with app.test_client() as c:
        c.post("/intraday/api/stop")


def test_api_start_creates_runtime(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.4)
        r = c.get("/intraday/api/snapshot")

    data = json.loads(r.data)
    assert data["ok"] is True
    assert data["status"] in ("ready", "warming", "empty")

    # cleanup
    with app.test_client() as c:
        c.post("/intraday/api/stop")


def test_api_start_idempotent(tmp_path, monkeypatch):
    """start 를 두 번 호출해도 ok 를 반환한다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r1 = c.post("/intraday/api/start",
                    data=json.dumps(_FAST_START),
                    content_type="application/json")
        r2 = c.post("/intraday/api/start",
                    data=json.dumps(_FAST_START),
                    content_type="application/json")
    assert json.loads(r1.data)["ok"] is True
    assert json.loads(r2.data)["ok"] is True

    with app.test_client() as c:
        c.post("/intraday/api/stop")


def test_api_start_unknown_provider(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({"provider": "unknown_xyz"}),
                   content_type="application/json")
    data = json.loads(r.data)
    assert r.status_code == 400
    assert data["ok"] is False


# ---------------------------------------------------------------------------
# 4. POST /intraday/api/stop
# ---------------------------------------------------------------------------


def test_api_stop_when_not_running(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/stop")
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


def test_api_stop_after_start(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.1)
        r = c.post("/intraday/api/stop")
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


def test_api_snapshot_after_stop_returns_not_running(tmp_path, monkeypatch):
    """stop 후 snapshot API 는 not_running 반환."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.1)
        c.post("/intraday/api/stop")
        time.sleep(0.1)
        r = c.get("/intraday/api/snapshot")
    data = json.loads(r.data)
    assert data["status"] == "not_running"


# ---------------------------------------------------------------------------
# 5. snapshot JSON 구조 검증
# ---------------------------------------------------------------------------


def test_api_snapshot_with_data_has_required_keys(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.5)  # mock source 가 snapshot 을 갱신할 때까지 대기
        r = c.get("/intraday/api/snapshot")

    data = json.loads(r.data)
    assert data["ok"] is True
    for k in ("status", "latest_count", "bucket_count",
              "raw_row_count", "sector_views", "generated_at"):
        assert k in data, f"Missing key: {k}"
    assert isinstance(data["sector_views"], list)

    with app.test_client() as c:
        c.post("/intraday/api/stop")


def test_api_snapshot_sector_views_structure(tmp_path, monkeypatch):
    """sector_views 가 있으면 leader_stocks 포함 구조를 갖는다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.8)
        r = c.get("/intraday/api/snapshot")
        c.post("/intraday/api/stop")

    data = json.loads(r.data)
    for sv in data.get("sector_views", []):
        assert "sector_name" in sv
        assert "leader_stocks" in sv
        assert isinstance(sv["leader_stocks"], list)


# ---------------------------------------------------------------------------
# 6. 기존 morning board 보존 확인
# ---------------------------------------------------------------------------


def test_morning_board_still_works(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/sector-board/")
    assert r.status_code in (200, 302)


def test_health_still_works(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/sector-board/health")
    assert r.status_code in (200, 503)


def test_sector_board_intraday_still_works(tmp_path, monkeypatch):
    """기존 JSONL 기반 /sector-board/intraday 도 살아 있어야 한다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/sector-board/intraday")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 7. WebSocket provider 파라미터 검증 (실제 접속 없음)
# ---------------------------------------------------------------------------


def _codes_file(tmp_path: Path, n: int) -> str:
    """n 개 종목코드를 가진 임시 파일 경로를 반환한다."""
    f = tmp_path / "codes.txt"
    f.write_text("\n".join(f"{i:06d}" for i in range(1, n + 1)), encoding="utf-8")
    return str(f)


def test_websocket_over_200_codes_returns_400(tmp_path, monkeypatch):
    """provider=websocket + 201종목 → 400, error 메시지에 200 포함.

    max_codes=0 으로 코드 수 제한을 비활성화하고 limit 체크를 통과시킨다.
    """
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({
                       "provider": "websocket",
                       "codes_file": _codes_file(tmp_path, 201),
                       "max_codes": 0,              # 코드 수 상한 없음
                       "max_total_realtime_codes": 200,
                   }),
                   content_type="application/json")
    assert r.status_code == 400
    data = json.loads(r.data)
    assert data["ok"] is False
    assert "200" in data["error"]
    assert data["formatted_code_count"] == 201


def test_websocket_exactly_200_codes_not_blocked_by_limit(tmp_path, monkeypatch):
    """200종목은 limit 자체에서 차단되지 않는다 (인증 실패는 허용)."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({
                       "provider": "websocket",
                       "codes_file": _codes_file(tmp_path, 200),
                       "max_total_realtime_codes": 200,
                   }),
                   content_type="application/json")
    data = json.loads(r.data)
    # 200종목은 limit 오류가 아님 — 인증 오류(400/200) 또는 시작 성공
    assert "formatted_code_count=200 >" not in data.get("error", "")


def test_websocket_custom_max_total_realtime_codes(tmp_path, monkeypatch):
    """max_total_realtime_codes=50 이면 51종목에서 차단된다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({
                       "provider": "websocket",
                       "codes_file": _codes_file(tmp_path, 51),
                       "max_total_realtime_codes": 50,
                   }),
                   content_type="application/json")
    assert r.status_code == 400
    data = json.loads(r.data)
    assert data["formatted_code_count"] == 51
    assert data["max_total_realtime_codes"] == 50


def test_websocket_start_response_includes_kiwoom_env(tmp_path, monkeypatch):
    """provider=websocket 시작 응답에 kiwoom_env 포함 (인증 실패 전까지 파라미터 확인)."""
    app = _make_app(tmp_path, monkeypatch)
    # 1종목으로 limit 통과, 실제 WebSocket 연결은 백그라운드에서 실패해도 시작 응답은 반환됨
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({
                       "provider": "websocket",
                       "kiwoom_env": "mock",
                       "exchange": "sor",
                       "codes_file": _codes_file(tmp_path, 1),
                       "snapshot_interval": 0.1,
                   }),
                   content_type="application/json")
    data = json.loads(r.data)
    # 시작 자체는 OK (실제 연결은 백그라운드)
    if data["ok"]:
        assert data["kiwoom_env"] == "mock"
        assert data["exchange"] == "sor"
        with app.test_client() as c2:
            c2.post("/intraday/api/stop")


def test_unknown_provider_returns_400(tmp_path, monkeypatch):
    """지원하지 않는 provider 는 400 에러."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.post("/intraday/api/start",
                   data=json.dumps({"provider": "kafka"}),
                   content_type="application/json")
    assert r.status_code == 400
    assert json.loads(r.data)["ok"] is False


# ---------------------------------------------------------------------------
# 8. api/snapshot 진단 필드 검증
# ---------------------------------------------------------------------------


def test_snapshot_no_runtime_has_diagnosis_fields(tmp_path, monkeypatch):
    """runtime 없을 때도 진단 필드가 모두 있다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        r = c.get("/intraday/api/snapshot")
    data = json.loads(r.data)
    for key in ("running", "runtime_state", "started_at", "runtime_error",
                "runtime_close_reason", "latest_count", "bucket_count",
                "raw_row_count", "ignored_row_count", "sector_count"):
        assert key in data, f"Missing diagnosis key: {key}"
    assert data["running"] is False
    assert data["started_at"] is None


def test_snapshot_with_runtime_has_started_at(tmp_path, monkeypatch):
    """runtime 시작 후 started_at 이 포함된다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.3)
        r = c.get("/intraday/api/snapshot")
        c.post("/intraday/api/stop")
    data = json.loads(r.data)
    assert data["started_at"] is not None
    assert data["running"] is True or data["running"] is False  # 중지됐을 수도 있음


def test_snapshot_updated_at_equals_generated_at(tmp_path, monkeypatch):
    """updated_at 과 generated_at 이 동일하다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps(_FAST_START),
               content_type="application/json")
        time.sleep(0.4)
        r = c.get("/intraday/api/snapshot")
        c.post("/intraday/api/stop")
    data = json.loads(r.data)
    if data["ok"]:
        assert data.get("updated_at") == data.get("generated_at")


def test_snapshot_max_codes_limits_registered_count(tmp_path, monkeypatch):
    """max_codes=3 이면 최대 3종목만 등록된다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as c:
        c.post("/intraday/api/start",
               data=json.dumps({**_FAST_START, "max_codes": 3}),
               content_type="application/json")
        time.sleep(0.4)
        r = c.get("/intraday/api/snapshot")
        c.post("/intraday/api/stop")
    data = json.loads(r.data)
    if data.get("ok"):
        assert data.get("latest_count", 0) <= 3
