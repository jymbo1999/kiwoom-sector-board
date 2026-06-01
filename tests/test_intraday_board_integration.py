from __future__ import annotations

from datetime import datetime

import pandas as pd

import sector_board
from sector_board import create_app
from sector_board.repository import upsert_snapshot
from src.market_data import get_intraday_board_view_models
from src.universe_builder import UniverseBuildConfig, build_universe


def test_mock_intraday_pipeline_renders_flask_board(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("INTRADAY_PROVIDER", "mock")
    monkeypatch.setenv("INTRADAY_BOARD_ENABLED", "true")
    monkeypatch.setattr(sector_board, "_setup_scheduler", lambda _database_url: None)
    database_url = f"sqlite:///{tmp_path / 'sector.db'}"
    app = create_app(
        {
            "TESTING": True,
            "SECTOR_BOARD_DATABASE_URL": database_url,
            "SECTOR_BOARD_AUTO_CREATE_TABLE": True,
        }
    )
    krx_data = pd.DataFrame(
        [
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI", "Marcap": 900_000_000_000, "Amount": 230_000_000_000},
            {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI", "Marcap": 800_000_000_000, "Amount": 190_000_000_000},
            {"Code": "042700", "Name": "한미반도체", "Market": "KOSPI", "Marcap": 700_000_000_000, "Amount": 80_000_000_000},
            {"Code": "329180", "Name": "HD현대중공업", "Market": "KOSPI", "Marcap": 600_000_000_000, "Amount": 85_000_000_000},
        ]
    )
    theme_map = pd.DataFrame(
        [
            {"code": "005930", "name": "삼성전자", "theme1": "반도체", "theme2": "", "theme3": ""},
            {"code": "000660", "name": "SK하이닉스", "theme1": "반도체", "theme2": "", "theme3": ""},
            {"code": "042700", "name": "한미반도체", "theme1": "반도체", "theme2": "", "theme3": ""},
            {"code": "329180", "name": "HD현대중공업", "theme1": "조선", "theme2": "", "theme3": ""},
        ]
    )
    universe_result = build_universe(
        krx_data,
        theme_map,
        UniverseBuildConfig(min_market_cap=0, min_trade_value=0, max_codes=300),
        generated_at=datetime(2026, 6, 1, 9, 30),
    )
    quotes = pd.DataFrame(
        [
            {"code": "005930", "name": "삼성전자", "current_price": 70100, "open_price": 68000, "prev_close": 67000, "change_rate": 5.2, "volume": 1000, "trade_value": 230_000_000_000, "accumulated_trade_value": 230_000_000_000, "minute_trade_value": 1_000_000, "updated_at": "2026-06-01T09:29:45"},
            {"code": "000660", "name": "SK하이닉스", "current_price": 232400, "open_price": 225000, "prev_close": 222000, "change_rate": 4.1, "volume": 900, "trade_value": 190_000_000_000, "accumulated_trade_value": 190_000_000_000, "minute_trade_value": 900_000, "updated_at": "2026-06-01T09:29:45"},
            {"code": "042700", "name": "한미반도체", "current_price": 120000, "open_price": 117000, "prev_close": 116000, "change_rate": 3.6, "volume": 800, "trade_value": 80_000_000_000, "accumulated_trade_value": 80_000_000_000, "minute_trade_value": 800_000, "updated_at": "2026-06-01T09:29:45"},
            {"code": "329180", "name": "HD현대중공업", "current_price": 150000, "open_price": 146000, "prev_close": 144000, "change_rate": 3.9, "volume": 700, "trade_value": 85_000_000_000, "accumulated_trade_value": 85_000_000_000, "minute_trade_value": 700_000, "updated_at": "2026-06-01T09:29:45"},
        ]
    )
    payload = get_intraday_board_view_models(
        quotes=quotes,
        universe=universe_result.universe,
        generated_at=datetime(2026, 6, 1, 9, 30),
    )
    payload["snapshot_date"] = "2026-06-01"
    upsert_snapshot(payload, database_url=database_url)

    response = app.test_client().get("/sector-board/")

    assert response.status_code == 200
    assert "오늘의 주도섹터 Top 5".encode() in response.data
    assert "반도체".encode() in response.data
    assert "삼성전자".encode() in response.data
    assert b"MOCK" in response.data
