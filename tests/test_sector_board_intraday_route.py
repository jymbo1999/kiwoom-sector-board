"""sector_board /intraday route 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import sector_board
from sector_board import create_app


# ---------------------------------------------------------------------------
# 공통 app fixture
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path, monkeypatch, logs_dir: Path | None = None):
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_KRX_DATA", "false")
    monkeypatch.setattr(sector_board, "_setup_scheduler", lambda _: None)
    cfg: dict = {
        "TESTING": True,
        "SECTOR_BOARD_DATABASE_URL": f"sqlite:///{tmp_path / 'sector.db'}",
        "SECTOR_BOARD_AUTO_CREATE_TABLE": True,
        "SECTOR_BOARD_NO_AUTH": True,
    }
    if logs_dir is not None:
        cfg["INTRADAY_LOGS_DIR"] = str(logs_dir)
    return create_app(cfg)


def _make_snapshot_jsonl(logs_dir: Path, filename: str, rows: list[dict]) -> Path:
    f = logs_dir / filename
    f.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return f


def _ready_snapshot() -> dict:
    return {
        "generated_at": "2026-06-01T13:45:00",
        "minute_key": "1345",
        "status": "ready",
        "latest_count": 5,
        "unmapped_count": 0,
        "bucket_count": 5,
        "raw_row_count": 1000,
        "ignored_row_count": 2,
        "sector_count": 2,
        "sector_views": [
            {
                "rank": 1,
                "sector_name": "반도체",
                "sector_score": 1_000_000.0,
                "total_minute_trade_value": 5_000_000_000,
                "average_change_rate": 2.5,
                "rising_ratio": 0.8,
                "active_stock_count": 3,
                "leader_stocks": [
                    {
                        "rank": 1,
                        "base_code": "005930",
                        "exchange": "sor",
                        "close_price": 81200,
                        "last_change_rate": 1.82,
                        "minute_trade_value_delta": 8_840_000_000,
                        "display_badge": "대장",
                    },
                    {
                        "rank": 2,
                        "base_code": "000660",
                        "exchange": "sor",
                        "close_price": 182000,
                        "last_change_rate": 3.20,
                        "minute_trade_value_delta": 7_360_000_000,
                        "display_badge": "2등주",
                    },
                ],
            },
            {
                "rank": 2,
                "sector_name": "조선",
                "sector_score": 500_000.0,
                "total_minute_trade_value": 1_000_000_000,
                "average_change_rate": -0.5,
                "rising_ratio": 0.33,
                "active_stock_count": 2,
                "leader_stocks": [
                    {
                        "rank": 1,
                        "base_code": "042660",
                        "exchange": "sor",
                        "close_price": 25000,
                        "last_change_rate": -0.5,
                        "minute_trade_value_delta": 800_000_000,
                        "display_badge": "대장",
                    }
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# 1. 기본 route 접근
# ---------------------------------------------------------------------------


def test_intraday_route_exists(tmp_path: Path, monkeypatch) -> None:
    """GET /sector-board/intraday 가 200 을 반환한다 (JSONL 없어도 OK)."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    assert resp.status_code == 200


def test_intraday_route_returns_html(tmp_path: Path, monkeypatch) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    assert b"text/html" in resp.content_type.encode()


# ---------------------------------------------------------------------------
# 2. JSONL 없을 때 — empty 상태
# ---------------------------------------------------------------------------


def test_intraday_empty_state_no_jsonl(tmp_path: Path, monkeypatch) -> None:
    """JSONL 파일이 없으면 empty 상태 페이지가 반환된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # empty 상태 힌트 문구 또는 status badge 가 있어야 한다
    assert "NO DATA" in html or "empty" in html.lower()


def test_intraday_empty_shows_run_hint(tmp_path: Path, monkeypatch) -> None:
    """JSONL 없을 때 smoke script 실행 안내가 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "dump-snapshot-jsonl" in html


# ---------------------------------------------------------------------------
# 3. JSONL 있을 때 — ready 상태
# ---------------------------------------------------------------------------


def test_intraday_ready_state_with_jsonl(tmp_path: Path, monkeypatch) -> None:
    """JSONL 이 있으면 ready 상태 페이지가 반환된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [_ready_snapshot()]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "LIVE" in html or "ready" in html.lower()


def test_intraday_shows_sector_names(tmp_path: Path, monkeypatch) -> None:
    """섹터 이름이 화면에 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [_ready_snapshot()]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "반도체" in html
    assert "조선" in html


def test_intraday_shows_leader_badges(tmp_path: Path, monkeypatch) -> None:
    """대장주 badge 가 화면에 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [_ready_snapshot()]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "대장" in html
    assert "2등주" in html


def test_intraday_shows_stock_codes(tmp_path: Path, monkeypatch) -> None:
    """종목코드가 화면에 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [_ready_snapshot()]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "005930" in html
    assert "000660" in html


def test_intraday_shows_minute_key(tmp_path: Path, monkeypatch) -> None:
    """기준 분이 화면에 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [_ready_snapshot()]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "1345" in html


# ---------------------------------------------------------------------------
# 4. 가장 최신 JSONL 을 읽는지 확인
# ---------------------------------------------------------------------------


def test_intraday_reads_most_recent_jsonl(tmp_path: Path, monkeypatch) -> None:
    """여러 JSONL 파일이 있을 때 가장 최신 파일의 마지막 줄을 읽는다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    old_snap = dict(_ready_snapshot(), minute_key="0900", sector_views=[])
    new_snap = dict(_ready_snapshot(), minute_key="1345")
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_090000.jsonl", [old_snap]
    )
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [new_snap]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "1345" in html


def test_intraday_reads_last_line_of_jsonl(tmp_path: Path, monkeypatch) -> None:
    """JSONL 파일에 여러 줄이 있을 때 마지막 줄을 읽는다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    first_snap = dict(_ready_snapshot(), minute_key="0900", sector_views=[])
    last_snap = dict(_ready_snapshot(), minute_key="1400")
    _make_snapshot_jsonl(
        logs_dir,
        "intraday_snapshot_20260601_134500.jsonl",
        [first_snap, last_snap],
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "1400" in html


# ---------------------------------------------------------------------------
# 5. warming 상태
# ---------------------------------------------------------------------------


def test_intraday_warming_state(tmp_path: Path, monkeypatch) -> None:
    """warming 상태가 화면에 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    warming = dict(_ready_snapshot(), status="warming", sector_views=[], sector_count=0)
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [warming]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "WARMING" in html or "warming" in html.lower()


# ---------------------------------------------------------------------------
# 6. 기존 morning board route 가 깨지지 않는지 확인
# ---------------------------------------------------------------------------


def test_morning_board_route_still_works(tmp_path: Path, monkeypatch) -> None:
    """기존 /sector-board/ route 가 여전히 동작한다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/")
    # DB 없어도 500이 아닌 200 또는 redirect 응답이어야 한다
    assert resp.status_code in (200, 302)


def test_health_route_still_works(tmp_path: Path, monkeypatch) -> None:
    """기존 /sector-board/health route 가 여전히 동작한다."""
    app = _make_app(tmp_path, monkeypatch)
    with app.test_client() as client:
        resp = client.get("/sector-board/health")
    assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# 7. unmapped_count 표시
# ---------------------------------------------------------------------------


def test_intraday_shows_unmapped_warning(tmp_path: Path, monkeypatch) -> None:
    """unmapped_count > 0 이면 미매핑 경고가 표시된다."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    snap = dict(_ready_snapshot(), unmapped_count=5)
    _make_snapshot_jsonl(
        logs_dir, "intraday_snapshot_20260601_134500.jsonl", [snap]
    )
    app = _make_app(tmp_path, monkeypatch, logs_dir=logs_dir)
    with app.test_client() as client:
        resp = client.get("/sector-board/intraday")
    html = resp.data.decode("utf-8")
    assert "미매핑" in html
    assert "5" in html
