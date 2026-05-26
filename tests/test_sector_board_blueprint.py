from __future__ import annotations

from sector_board import create_app
from sector_board.repository import upsert_snapshot


def test_sector_board_index_renders_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_url = f"sqlite:///{tmp_path / 'sector.db'}"
    app = create_app(
        {
            "TESTING": True,
            "SECTOR_BOARD_DATABASE_URL": database_url,
            "SECTOR_BOARD_AUTO_CREATE_TABLE": True,
        }
    )
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


def test_sector_board_api_reports_missing_database(monkeypatch) -> None:
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app({"TESTING": True})

    response = app.test_client().get("/sector-board/api/snapshot")

    assert response.status_code == 503
    assert response.get_json()["ok"] is False
