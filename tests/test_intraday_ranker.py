from __future__ import annotations

import pandas as pd

from src.sector_ranker import rank_intraday_leaders, rank_sectors


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"code": "100001", "name": "Broad A", "sector": "반도체", "theme": "Broad", "market": "KOSPI", "market_cap": 900, "source": "test"},
            {"code": "100002", "name": "Broad B", "sector": "반도체", "theme": "Broad", "market": "KOSPI", "market_cap": 800, "source": "test"},
            {"code": "100003", "name": "Broad C", "sector": "반도체", "theme": "Broad", "market": "KOSPI", "market_cap": 700, "source": "test"},
            {"code": "200001", "name": "Spike A", "sector": "테마주", "theme": "Spike", "market": "KOSDAQ", "market_cap": 100, "source": "test"},
            {"code": "300001", "name": "Liquid A", "sector": "조선", "theme": "Liquid", "market": "KOSPI", "market_cap": 900, "source": "test"},
            {"code": "300002", "name": "Liquid B", "sector": "조선", "theme": "Liquid", "market": "KOSPI", "market_cap": 800, "source": "test"},
            {"code": "400001", "name": "Robot A", "sector": "로봇", "theme": "Robot", "market": "KOSDAQ", "market_cap": 600, "source": "test"},
            {"code": "500001", "name": "Bio A", "sector": "바이오", "theme": "Bio", "market": "KOSDAQ", "market_cap": 600, "source": "test"},
            {"code": "600001", "name": "Auto A", "sector": "자동차", "theme": "Auto", "market": "KOSPI", "market_cap": 600, "source": "test"},
            {"code": "700001", "name": "Game A", "sector": "게임", "theme": "Game", "market": "KOSDAQ", "market_cap": 600, "source": "test"},
        ]
    )


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"code": "100001", "name": "Broad A", "current_price": 105, "open_price": 100, "prev_close": 100, "change_rate": 5.0, "volume": 1000, "trade_value": 100_000, "accumulated_trade_value": 100_000, "minute_trade_value": 10_000},
            {"code": "100002", "name": "Broad B", "current_price": 104, "open_price": 100, "prev_close": 100, "change_rate": 4.0, "volume": 900, "trade_value": 90_000, "accumulated_trade_value": 90_000, "minute_trade_value": 9_000},
            {"code": "100003", "name": "Broad C", "current_price": 103, "open_price": 100, "prev_close": 100, "change_rate": 3.0, "volume": 800, "trade_value": 80_000, "accumulated_trade_value": 80_000, "minute_trade_value": 8_000},
            {"code": "200001", "name": "Spike A", "current_price": 125, "open_price": 100, "prev_close": 100, "change_rate": 25.0, "volume": 10, "trade_value": 1_000, "accumulated_trade_value": 1_000, "minute_trade_value": 50},
            {"code": "300001", "name": "Liquid A", "current_price": 106, "open_price": 100, "prev_close": 100, "change_rate": 6.0, "volume": 2000, "trade_value": 200_000, "accumulated_trade_value": 200_000, "minute_trade_value": 20_000},
            {"code": "300002", "name": "Liquid B", "current_price": 102, "open_price": 100, "prev_close": 100, "change_rate": 2.0, "volume": 500, "trade_value": 60_000, "accumulated_trade_value": 60_000, "minute_trade_value": 6_000},
            {"code": "400001", "name": "Robot A", "current_price": 102, "open_price": 100, "prev_close": 100, "change_rate": 2.0, "volume": 100, "trade_value": 20_000, "accumulated_trade_value": 20_000, "minute_trade_value": 2_000},
            {"code": "500001", "name": "Bio A", "current_price": 101, "open_price": 100, "prev_close": 100, "change_rate": 1.0, "volume": 100, "trade_value": 10_000, "accumulated_trade_value": 10_000, "minute_trade_value": 1_000},
            {"code": "600001", "name": "Auto A", "current_price": 100, "open_price": 100, "prev_close": 100, "change_rate": 0.0, "volume": 100, "trade_value": 5_000, "accumulated_trade_value": 5_000, "minute_trade_value": 500},
            {"code": "700001", "name": "Game A", "current_price": 99, "open_price": 100, "prev_close": 100, "change_rate": -1.0, "volume": 100, "trade_value": 4_000, "accumulated_trade_value": 4_000, "minute_trade_value": 400},
        ]
    )


def test_existing_rank_sectors_still_works() -> None:
    prices = pd.DataFrame(
        [
            {"code": "111111", "name": "A", "change_rate": 10.0, "trade_value": 1000, "volume": 10, "open_price": 90, "current_price": 100},
            {"code": "222222", "name": "B", "change_rate": 2.0, "trade_value": 500, "volume": 10, "open_price": 98, "current_price": 100},
        ]
    )
    theme_map = pd.DataFrame(
        [
            {"code": "111111", "name": "A", "theme1": "AI", "theme2": "", "theme3": ""},
            {"code": "222222", "name": "B", "theme1": "AI", "theme2": "", "theme3": ""},
        ]
    )

    sectors, leaders = rank_sectors(prices, theme_map)

    assert not sectors.empty
    assert leaders.sort_values("rank").iloc[0]["code"] == "111111"


def test_high_change_and_trade_stock_becomes_top_leader() -> None:
    result = rank_intraday_leaders(_quotes(), _universe())

    liquid_leaders = [row for row in result["leaders"] if row["theme_name"] == "Liquid"]

    assert liquid_leaders[0]["code"] == "300001"
    assert liquid_leaders[0]["leader_score"] > liquid_leaders[1]["leader_score"]


def test_broad_rally_scores_above_single_low_trade_spike() -> None:
    result = rank_intraday_leaders(_quotes(), _universe())
    ranks = {row["theme_name"]: row["rank"] for row in result["themes"]}

    assert ranks["Broad"] < ranks["Spike"]


def test_low_trade_spike_does_not_become_first_theme() -> None:
    result = rank_intraday_leaders(_quotes(), _universe())

    assert result["themes"][0]["theme_name"] != "Spike"


def test_top_five_sector_limit_and_leader_limit_are_enforced() -> None:
    result = rank_intraday_leaders(_quotes(), _universe(), theme_limit=5, leader_limit=3)

    assert len(result["themes"]) == 5
    assert {row["rank"] for row in result["themes"]} == {1.0, 2.0, 3.0, 4.0, 5.0}
    per_theme_counts = pd.DataFrame(result["leaders"]).groupby("theme_name")["code"].count()
    assert per_theme_counts.max() <= 3


def test_previous_snapshot_generates_new_drop_and_rank_change_events() -> None:
    previous = {
        "themes": [
            {"rank": 1, "theme_name": "Spike"},
            {"rank": 2, "theme_name": "Old"},
            {"rank": 3, "theme_name": "Broad"},
        ]
    }

    result = rank_intraday_leaders(_quotes(), _universe(), previous_snapshot=previous)
    event_types = {(row["event_type"], row["theme_name"]) for row in result["rank_events"]}

    assert ("rank_up", "Broad") in event_types
    assert ("rank_down", "Spike") in event_types
    assert ("dropped", "Old") in event_types
    assert any(event_type == "new_entry" for event_type, _theme in event_types)


def test_string_numeric_values_and_missing_trade_values_are_defensive() -> None:
    quotes = pd.DataFrame(
        [
            {"code": "100001", "name": "Broad A", "current_price": "+105", "open_price": "100", "prev_close": "100", "change_rate": "5.0", "volume": "1,000", "trade_value": "0", "accumulated_trade_value": "", "minute_trade_value": "10,000"},
        ]
    )

    result = rank_intraday_leaders(quotes, _universe().head(1))

    assert result["summary"]["stock_count"] == 1
    assert result["leaders"][0]["trade_value"] == 105000.0
