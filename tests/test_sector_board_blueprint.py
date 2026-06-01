from __future__ import annotations

from typing import Any

import sector_board
from sector_board import create_app
from sector_board.repository import upsert_snapshot


def _make_app(tmp_path, monkeypatch, *, auto_create: bool = True):
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_KRX_DATA", "false")
    monkeypatch.setattr(sector_board, "_setup_scheduler", lambda _database_url: None)
    database_url = f"sqlite:///{tmp_path / 'sector.db'}"
    app = create_app(
        {
            "TESTING": True,
            "SECTOR_BOARD_DATABASE_URL": database_url,
            "SECTOR_BOARD_AUTO_CREATE_TABLE": auto_create,
        }
    )
    return app, database_url


def _intraday_snapshot() -> dict[str, Any]:
    return {
        "snapshot_date": "2026-06-01",
        "generated_at": "2026-06-01T09:30:00",
        "summary": {
            "board_type": "intraday",
            "data_mode": "mock",
            "provider_mode": "mock",
            "generated_at": "2026-06-01T09:30:00",
            "freshness_seconds": 15,
            "theme_count": 2,
            "stock_count": 4,
            "top_theme": "반도체",
            "avg_change_rate": 5.1,
        },
        "themes": [
            {
                "rank": 1,
                "theme_id": "반도체",
                "theme_name": "반도체",
                "theme_score": 8.8,
                "total_trading_value": 1_200_000_000_000,
                "top5_change_rate_mean": 4.8,
                "excess_return": 3.1,
                "rising_ratio": 1.0,
            },
            {
                "rank": 2,
                "theme_id": "조선",
                "theme_name": "조선",
                "theme_score": 7.2,
                "total_trading_value": 850_000_000_000,
                "top5_change_rate_mean": 3.9,
                "excess_return": 2.4,
                "rising_ratio": 0.75,
            },
        ],
        "leaders": [
            {
                "theme_id": "반도체",
                "rank": 1,
                "name": "삼성전자",
                "code": "005930",
                "current_price": 70_100,
                "change_rate": 5.2,
                "trade_value": 230_000_000_000,
                "leader_score": 9.2,
            },
            {
                "theme_id": "반도체",
                "rank": 2,
                "name": "SK하이닉스",
                "code": "000660",
                "current_price": 232_400,
                "change_rate": 4.1,
                "trade_value": 190_000_000_000,
                "leader_score": 8.7,
            },
            {
                "theme_id": "반도체",
                "rank": 3,
                "name": "한미반도체",
                "code": "042700",
                "current_price": 120_000,
                "change_rate": 3.6,
                "trade_value": 80_000_000_000,
                "leader_score": 7.5,
            },
            {
                "theme_id": "반도체",
                "rank": 4,
                "name": "테스트4",
                "code": "000004",
                "current_price": 40_000,
                "change_rate": 2.1,
                "trade_value": 1_000_000_000,
                "leader_score": 3.0,
            },
            {
                "theme_id": "반도체",
                "rank": 5,
                "name": "테스트5",
                "code": "000005",
                "current_price": 50_000,
                "change_rate": 1.1,
                "trade_value": 900_000_000,
                "leader_score": 2.7,
            },
            {
                "theme_id": "반도체",
                "rank": 6,
                "name": "숨김종목",
                "code": "000006",
                "current_price": 60_000,
                "change_rate": 0.1,
                "trade_value": 800_000_000,
                "leader_score": 1.0,
            },
            {
                "theme_id": "조선",
                "rank": 1,
                "name": "HD현대중공업",
                "code": "329180",
                "current_price": 150_000,
                "change_rate": 3.9,
                "trade_value": 85_000_000_000,
                "leader_score": 8.1,
            },
        ],
        "rank_events": [
            {
                "event_type": "rank_up",
                "theme_name": "반도체",
                "previous_rank": 3,
                "current_rank": 1,
            }
        ],
        "provider_status": {
            "mode": "intraday_snapshot",
            "provider_mode": "mock",
            "matched_count": 4,
        },
    }


def test_sector_board_index_renders_snapshot(tmp_path, monkeypatch) -> None:
    app, database_url = _make_app(tmp_path, monkeypatch)
    upsert_snapshot(
        {
            "generated_at": "2026-05-26T09:05:00",
            "summary": {"theme_count": 1, "stock_count": 2, "top_theme": "AI", "avg_change_rate": 3.2},
            "themes": [
                {
                    "theme_id": "AI",
                    "theme_name": "AI",
                    "theme_score": 92.5,
                    "total_trading_value": 150_000_000_000,
                    "top5_change_rate_mean": 6.5,
                }
            ],
            "leaders": [
                {
                    "theme_id": "AI",
                    "rank": 1,
                    "name": "A",
                    "code": "000001",
                    "change_rate": 7.0,
                    "trade_value": 80_000_000_000,
                }
            ],
        },
        database_url=database_url,
    )

    response = app.test_client().get("/sector-board/")

    assert response.status_code == 200
    assert "오늘의 주도섹터".encode() in response.data
    assert "AI".encode() in response.data
    assert "000001".encode() in response.data
    assert "오늘의 주도섹터 Top 5".encode() not in response.data


def test_sector_board_index_renders_intraday_leaderboard(tmp_path, monkeypatch) -> None:
    app, database_url = _make_app(tmp_path, monkeypatch)
    upsert_snapshot(_intraday_snapshot(), database_url=database_url)

    response = app.test_client().get("/sector-board/")

    assert response.status_code == 200
    assert "오늘의 주도섹터 Top 5".encode() in response.data
    assert "반도체".encode() in response.data
    assert "삼성전자".encode() in response.data
    assert "005930".encode() in response.data
    assert "SK하이닉스".encode() in response.data
    assert "000660".encode() in response.data
    assert "한미반도체".encode() in response.data
    assert "042700".encode() in response.data
    assert "숨김종목".encode() not in response.data
    assert "교체 감지".encode() in response.data
    assert "데이터모드".encode() in response.data
    assert b"MOCK" in response.data
    assert b"intraday_snapshot" in response.data
    assert "매칭".encode() in response.data
    assert "실제 실시간 시세로 오해하지 않도록".encode() in response.data


def test_sector_board_api_reports_missing_database(monkeypatch) -> None:
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app({"TESTING": True})

    response = app.test_client().get("/sector-board/api/snapshot")

    assert response.status_code == 503
    assert response.get_json()["ok"] is False
