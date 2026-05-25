from __future__ import annotations

import pandas as pd

from src.sector_ranker import rank_sectors


def test_rank_sectors_scores_and_leaders() -> None:
    prices = pd.DataFrame(
        [
            {"code": "111111", "name": "A", "change_rate": 10.0, "trade_value": 1000, "volume": 10, "open_price": 90, "current_price": 100},
            {"code": "222222", "name": "B", "change_rate": 2.0, "trade_value": 500, "volume": 10, "open_price": 98, "current_price": 100},
            {"code": "333333", "name": "C", "change_rate": -1.0, "trade_value": 100, "volume": 10, "open_price": 101, "current_price": 100},
        ]
    )
    theme_map = pd.DataFrame(
        [
            {"code": "111111", "name": "A", "theme1": "AI", "theme2": "반도체", "theme3": ""},
            {"code": "222222", "name": "B", "theme1": "AI", "theme2": "", "theme3": ""},
            {"code": "333333", "name": "C", "theme1": "바이오", "theme2": "", "theme3": ""},
        ]
    )

    sectors, leaders = rank_sectors(prices, theme_map)

    assert "AI" in set(sectors["sector"])
    ai_leaders = leaders[leaders["sector"] == "AI"].sort_values("rank")
    assert ai_leaders.iloc[0]["code"] == "111111"
    assert sectors.loc[sectors["sector"] == "AI", "rising_ratio"].iloc[0] == 1.0
