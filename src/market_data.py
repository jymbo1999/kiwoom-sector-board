from __future__ import annotations

from datetime import datetime, time
from typing import Any

import pandas as pd

from .config import Settings, load_settings
from .dummy_data import load_sample_prices
from .kiwoom_client import KiwoomApiError, KiwoomRestClient
from .sector_ranker import rank_sectors
from .theme_loader import load_theme_map


MARKET_SUMMARY_KEYS = [
    "timestamp",
    "market_phase",
    "data_mode",
    "effective_mock",
    "error_message",
    "theme_count",
    "stock_count",
    "top_theme",
    "top_theme_score",
    "avg_change_rate",
    "rising_ratio",
    "total_trade_value",
]

THEME_HEATMAP_COLUMNS = [
    "theme_id",
    "theme_name",
    "sector_score",
    "theme_score",
    "trade_value_sum",
    "total_trading_value",
    "rising_ratio",
    "stock_count",
    "top5_change_rate_mean",
    "leader_names",
]

THEME_LEADER_COLUMNS = [
    "rank",
    "theme_id",
    "theme_name",
    "code",
    "name",
    "change_rate",
    "current_price",
    "trade_value",
    "volume",
    "leader_score",
]

THEME_TIMELINE_COLUMNS = [
    "date",
    "theme_id",
    "theme_name",
    "sector_score",
    "is_dummy_timeline",
]


def load_market_prices(settings: Settings, codes: list[str]) -> tuple[pd.DataFrame, str | None, bool]:
    if settings.use_mock:
        return load_sample_prices(settings.sample_prices_path), None, True

    client = KiwoomRestClient(
        base_url=settings.base_url,
        app_key=settings.app_key,
        secret_key=settings.secret_key,
    )
    try:
        return client.fetch_current_prices(codes), None, False
    except KiwoomApiError as exc:
        fallback = load_sample_prices(settings.sample_prices_path)
        return fallback, f"키움 API 조회에 실패해 샘플 데이터로 화면을 표시합니다: {exc}", True


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _get_market_phase(reference_time: datetime | None = None) -> str:
    current = reference_time or datetime.now()
    current_time = current.time()
    if time(8, 0) <= current_time < time(9, 0):
        return "pre_market"
    if time(9, 0) <= current_time < time(15, 30):
        return "regular_market"
    if time(15, 30) <= current_time < time(18, 0):
        return "after_market"
    return "closed"


def _load_ranked_snapshot() -> tuple[Settings, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None, bool]:
    settings = load_settings()
    theme_map = load_theme_map(settings.theme_map_path)
    codes = theme_map["code"].dropna().astype(str).drop_duplicates().tolist()
    prices, error_message, effective_mock = load_market_prices(settings, codes)
    sectors, leaders = rank_sectors(prices, theme_map, top_n=5)
    return settings, theme_map, prices, sectors, leaders, error_message, effective_mock


def _data_mode(settings: Settings, effective_mock: bool) -> str:
    if effective_mock:
        return "mock"
    if settings.use_mock:
        return "mock"
    return "kiwoom_rest"


def get_market_summary() -> dict[str, Any]:
    """Return stable market/theme summary values for Streamlit view models."""

    settings, theme_map, prices, sectors, _leaders, error_message, effective_mock = _load_ranked_snapshot()
    top_sector = sectors.iloc[0] if not sectors.empty else None

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "market_phase": _get_market_phase(),
        "data_mode": _data_mode(settings, effective_mock),
        "effective_mock": bool(effective_mock),
        "error_message": error_message,
        "theme_count": int(sectors["sector"].nunique()) if "sector" in sectors else 0,
        "stock_count": int(theme_map["code"].dropna().astype(str).nunique()) if "code" in theme_map else 0,
        "top_theme": None if top_sector is None else str(top_sector["sector"]),
        "top_theme_score": None if top_sector is None else float(top_sector["sector_score"]),
        "avg_change_rate": float(pd.to_numeric(prices["change_rate"], errors="coerce").mean()) if not prices.empty else 0.0,
        "rising_ratio": float((pd.to_numeric(prices["change_rate"], errors="coerce") > 0).mean()) if not prices.empty else 0.0,
        "total_trade_value": float(pd.to_numeric(prices["trade_value"], errors="coerce").fillna(0).sum()) if not prices.empty else 0.0,
    }
    return {key: summary[key] for key in MARKET_SUMMARY_KEYS}


def get_theme_heatmap() -> pd.DataFrame:
    """Return one stable row per theme/sector for future Streamlit or Plotly rendering."""

    _settings, _theme_map, _prices, sectors, leaders, _error_message, _effective_mock = _load_ranked_snapshot()
    if sectors.empty:
        return _empty_dataframe(THEME_HEATMAP_COLUMNS)

    heatmap = sectors.copy()
    heatmap["theme_id"] = heatmap["sector"].astype(str)
    heatmap["theme_name"] = heatmap["sector"].astype(str)
    heatmap["theme_score"] = pd.to_numeric(heatmap["sector_score"], errors="coerce").fillna(0.0)
    heatmap["total_trading_value"] = pd.to_numeric(heatmap["trade_value_sum"], errors="coerce").fillna(0.0)

    leader_names = (
        leaders.sort_values(["sector", "rank"])
        .groupby("sector")["name"]
        .apply(lambda names: ", ".join(names.astype(str).head(5)))
    )
    heatmap["leader_names"] = heatmap["sector"].map(leader_names).fillna("")

    return heatmap[THEME_HEATMAP_COLUMNS].reset_index(drop=True)


def get_theme_leaders(theme_id: str | None) -> pd.DataFrame:
    """Return Top 5 leaders for a theme id, or an empty stable frame when missing."""

    if not theme_id:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    _settings, _theme_map, _prices, _sectors, leaders, _error_message, _effective_mock = _load_ranked_snapshot()
    if leaders.empty or "sector" not in leaders:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    selected = leaders[leaders["sector"].astype(str) == str(theme_id)].sort_values("rank").head(5).copy()
    if selected.empty:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    selected["theme_id"] = selected["sector"].astype(str)
    selected["theme_name"] = selected["sector"].astype(str)
    return selected[THEME_LEADER_COLUMNS].reset_index(drop=True)


def get_theme_timeline(days: int = 5) -> pd.DataFrame:
    """Return a stable timeline schema without pretending snapshot data is history."""

    _ = days
    return _empty_dataframe(THEME_TIMELINE_COLUMNS)
