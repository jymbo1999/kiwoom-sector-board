from __future__ import annotations

import pandas as pd

from .dummy_data import REQUIRED_PRICE_COLUMNS
from .theme_loader import themes_to_long


def _min_max_to_10(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    min_value = numeric.min()
    max_value = numeric.max()
    if max_value == min_value:
        return pd.Series(10.0, index=series.index)
    return ((numeric - min_value) / (max_value - min_value)) * 10.0


def _rank_score(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if len(numeric) <= 1:
        return pd.Series(10.0, index=series.index)
    return numeric.rank(pct=True, method="average") * 10.0


def build_sector_universe(prices: pd.DataFrame, theme_map: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_PRICE_COLUMNS) - set(prices.columns)
    if missing:
        raise ValueError(f"price data is missing columns: {sorted(missing)}")

    long_theme = themes_to_long(theme_map)
    merged = long_theme.merge(prices, on=["code", "name"], how="inner")
    if merged.empty:
        raise ValueError("no matching rows between price data and theme map")

    numeric_columns = ["change_rate", "trade_value", "volume", "open_price", "current_price"]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)

    open_price = merged["open_price"].replace(0, pd.NA)
    merged["open_to_current_strength"] = (
        (merged["current_price"] - merged["open_price"]) / open_price * 10.0
    ).fillna(0.0)
    # TODO: Allow user-managed representative scores in theme_map.csv.
    merged["theme_representative_score"] = 1.0
    return merged


def add_leader_scores(universe: pd.DataFrame) -> pd.DataFrame:
    scored = universe.copy()
    scored["change_rate_rank_score"] = scored.groupby("sector")["change_rate"].transform(_rank_score)
    scored["trade_value_rank_score"] = scored.groupby("sector")["trade_value"].transform(_rank_score)
    scored["leader_score"] = (
        scored["change_rate_rank_score"] * 0.45
        + scored["trade_value_rank_score"] * 0.35
        + scored["open_to_current_strength"] * 0.10
        + scored["theme_representative_score"] * 0.10
    )
    return scored


def rank_sectors(prices: pd.DataFrame, theme_map: pd.DataFrame, top_n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = add_leader_scores(build_sector_universe(prices, theme_map))

    sector_rows = []
    leader_rows = []
    for sector, group in universe.groupby("sector", sort=False):
        top_by_change = group.nlargest(min(top_n, len(group)), "change_rate")
        leaders = group.sort_values(
            ["leader_score", "change_rate", "trade_value"],
            ascending=[False, False, False],
        ).head(top_n)

        sector_rows.append(
            {
                "sector": sector,
                "top5_change_rate_mean": top_by_change["change_rate"].mean(),
                "trade_value_sum": group["trade_value"].sum(),
                "rising_ratio": (group["change_rate"] > 0).mean(),
                "limit_up_count": int((group["change_rate"] >= 29.5).sum()),
                "stock_count": len(group),
            }
        )
        leader_rows.append(leaders.assign(rank=range(1, len(leaders) + 1)))

    sectors = pd.DataFrame(sector_rows)
    sectors["normalized_trade_value_sum"] = _min_max_to_10(sectors["trade_value_sum"])
    sectors["sector_score"] = (
        sectors["top5_change_rate_mean"] * 0.45
        + sectors["normalized_trade_value_sum"] * 0.30
        + sectors["rising_ratio"] * 20.0 * 0.15
        + sectors["limit_up_count"] * 2.0
    )
    sectors = sectors.sort_values(
        ["sector_score", "trade_value_sum"],
        ascending=[False, False],
    ).reset_index(drop=True)

    leaders = pd.concat(leader_rows, ignore_index=True)
    leaders["rank"] = leaders["rank"].astype(int)
    return sectors, leaders
