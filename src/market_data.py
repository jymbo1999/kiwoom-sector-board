from __future__ import annotations

from datetime import datetime, time
from typing import Any, Callable

import pandas as pd

from .config import Settings, load_settings
from .dummy_data import load_sample_prices
from .kiwoom_auth import KiwoomAuthError
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
    "market_cap",
    "rising_ratio",
    "stock_count",
    "top5_change_rate_mean",
    "leader_names",
    "leader_labels",
    "badges",
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
    "rank_1_theme",
    "rank_2_theme",
    "rank_3_theme",
    "top_leader_stock",
    "top_leader_change_rate",
    "total_trading_value",
    "market_comment",
    "badges",
]

MARKET_MOVER_KEYS = [
    "ticker",
    "name",
    "market",
    "sector",
    "pct_change",
    "volume_rank",
    "trading_value",
]

MOCK_MARKET_MOVERS: list[dict[str, Any]] = [
    {
        "ticker": "000660",
        "name": "SK하이닉스",
        "market": "KOSPI",
        "sector": "반도체",
        "pct_change": 8.7,
        "volume_rank": 2,
        "trading_value": 684_200_000_000,
    },
    {
        "ticker": "064350",
        "name": "현대로템",
        "market": "KOSPI",
        "sector": "방산",
        "pct_change": 7.9,
        "volume_rank": 5,
        "trading_value": 312_800_000_000,
    },
    {
        "ticker": "042700",
        "name": "한미반도체",
        "market": "KOSPI",
        "sector": "반도체",
        "pct_change": 7.4,
        "volume_rank": 4,
        "trading_value": 278_500_000_000,
    },
    {
        "ticker": "247540",
        "name": "에코프로비엠",
        "market": "KOSDAQ",
        "sector": "2차전지",
        "pct_change": 6.8,
        "volume_rank": 7,
        "trading_value": 221_300_000_000,
    },
    {
        "ticker": "329180",
        "name": "HD현대중공업",
        "market": "KOSPI",
        "sector": "조선",
        "pct_change": 6.2,
        "volume_rank": 8,
        "trading_value": 198_400_000_000,
    },
    {
        "ticker": "207940",
        "name": "삼성바이오로직스",
        "market": "KOSPI",
        "sector": "바이오",
        "pct_change": 5.6,
        "volume_rank": 10,
        "trading_value": 174_600_000_000,
    },
    {
        "ticker": "277810",
        "name": "레인보우로보틱스",
        "market": "KOSDAQ",
        "sector": "로봇",
        "pct_change": 5.1,
        "volume_rank": 11,
        "trading_value": 143_900_000_000,
    },
    {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "sector": "AI",
        "pct_change": 4.8,
        "volume_rank": 1,
        "trading_value": 1_234_567_890_000,
    },
    {
        "ticker": "034020",
        "name": "두산에너빌리티",
        "market": "KOSPI",
        "sector": "원전",
        "pct_change": 4.3,
        "volume_rank": 3,
        "trading_value": 356_700_000_000,
    },
    {
        "ticker": "003670",
        "name": "포스코퓨처엠",
        "market": "KOSPI",
        "sector": "2차전지",
        "pct_change": 3.9,
        "volume_rank": 9,
        "trading_value": 166_200_000_000,
    },
    {
        "ticker": "012450",
        "name": "한화에어로스페이스",
        "market": "KOSPI",
        "sector": "방산",
        "pct_change": 3.5,
        "volume_rank": 6,
        "trading_value": 244_100_000_000,
    },
    {
        "ticker": "145020",
        "name": "휴젤",
        "market": "KOSDAQ",
        "sector": "바이오",
        "pct_change": 2.8,
        "volume_rank": 15,
        "trading_value": 88_300_000_000,
    },
]

def load_market_prices(
    settings: Settings,
    codes: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, str | None, bool]:
    if settings.use_mock:
        return load_sample_prices(settings.sample_prices_path), None, True

    client = KiwoomRestClient(
        base_url=settings.base_url,
        app_key=settings.app_key,
        secret_key=settings.secret_key,
        timeout=settings.api_timeout_seconds,
        retry_count=settings.api_retry_count,
        backoff_seconds=settings.api_request_interval_seconds,
    )
    try:
        return client.fetch_current_prices(codes, on_progress=on_progress), None, False
    except (KiwoomApiError, KiwoomAuthError) as exc:
        fallback = load_sample_prices(settings.sample_prices_path)
        return fallback, f"키움 API 조회에 실패해 샘플 데이터로 화면을 표시합니다: {exc}", True


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


_REFRESH_CHECKPOINTS: list[time] = [time(9, 3), time(9, 15), time(10, 0)]


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


def get_refresh_schedule(now: datetime | None = None) -> dict[str, Any]:
    """Return next/last checkpoint info for the auto-refresh logic.

    Keys:
      next_checkpoint  – datetime of the next scheduled refresh, or None
      last_checkpoint  – datetime of the last passed checkpoint today, or None
      seconds_until    – int seconds until next_checkpoint, or None
      market_phase     – string from _get_market_phase
    """
    current = now or datetime.now()
    today = current.date()
    checkpoints = [datetime.combine(today, t) for t in _REFRESH_CHECKPOINTS]

    past = [cp for cp in checkpoints if cp <= current]
    upcoming = [cp for cp in checkpoints if cp > current]

    next_cp = upcoming[0] if upcoming else None
    last_cp = past[-1] if past else None
    seconds_until = int((next_cp - current).total_seconds()) if next_cp else None

    return {
        "next_checkpoint": next_cp,
        "last_checkpoint": last_cp,
        "seconds_until": seconds_until,
        "market_phase": _get_market_phase(current),
    }


def _load_ranked_snapshot(
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[Settings, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None, bool]:
    settings = load_settings()
    theme_map = load_theme_map(settings.theme_map_path)
    codes = theme_map["code"].dropna().astype(str).drop_duplicates().tolist()
    if settings.morning_board_max_codes:
        codes = codes[: settings.morning_board_max_codes]
    prices, error_message, effective_mock = load_market_prices(settings, codes, on_progress=on_progress)
    sectors, leaders = rank_sectors(prices, theme_map, top_n=5)
    return settings, theme_map, prices, sectors, leaders, error_message, effective_mock


def _data_mode(settings: Settings, effective_mock: bool) -> str:
    if effective_mock:
        return "mock"
    if settings.use_mock:
        return "mock"
    return "kiwoom_rest"


def _build_market_summary(
    settings: Settings,
    theme_map: pd.DataFrame,
    prices: pd.DataFrame,
    sectors: pd.DataFrame,
    error_message: str | None,
    effective_mock: bool,
) -> dict[str, Any]:
    top_sector = sectors.iloc[0] if not sectors.empty else None

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "market_phase": _get_market_phase(),
        "data_mode": _data_mode(settings, effective_mock),
        "effective_mock": bool(effective_mock),
        "error_message": error_message,
        "theme_count": int(sectors["sector"].nunique()) if "sector" in sectors else 0,
        "stock_count": int(prices["code"].dropna().astype(str).nunique()) if "code" in prices else 0,
        "top_theme": None if top_sector is None else str(top_sector["sector"]),
        "top_theme_score": None if top_sector is None else float(top_sector["sector_score"]),
        "avg_change_rate": float(pd.to_numeric(prices["change_rate"], errors="coerce").mean()) if not prices.empty else 0.0,
        "rising_ratio": float((pd.to_numeric(prices["change_rate"], errors="coerce") > 0).mean()) if not prices.empty else 0.0,
        "total_trade_value": float(pd.to_numeric(prices["trade_value"], errors="coerce").fillna(0).sum()) if not prices.empty else 0.0,
    }
    return {key: summary[key] for key in MARKET_SUMMARY_KEYS}


def _build_theme_heatmap(sectors: pd.DataFrame, leaders: pd.DataFrame) -> pd.DataFrame:
    if sectors.empty:
        return _empty_dataframe(THEME_HEATMAP_COLUMNS)

    heatmap = sectors.copy()
    heatmap["theme_id"] = heatmap["sector"].astype(str)
    heatmap["theme_name"] = heatmap["sector"].astype(str)
    heatmap["theme_score"] = pd.to_numeric(heatmap["sector_score"], errors="coerce").fillna(0.0)
    heatmap["total_trading_value"] = pd.to_numeric(heatmap["trade_value_sum"], errors="coerce").fillna(0.0)
    # market_cap: real data = sum of constituent stock market caps.
    # Mock fallback uses theme_score * stock_count so the distribution differs from trading value.
    _ts = pd.to_numeric(heatmap["theme_score"], errors="coerce").fillna(1.0).clip(lower=0.1)
    _sc = pd.to_numeric(heatmap["stock_count"], errors="coerce").fillna(1.0)
    heatmap["market_cap"] = (_ts * _sc * 100_000_000_000).round()

    leader_names = (
        leaders.sort_values(["sector", "rank"])
        .groupby("sector")["name"]
        .apply(lambda names: ", ".join(names.astype(str).head(5)))
    )
    heatmap["leader_names"] = heatmap["sector"].map(leader_names).fillna("")

    def _format_leader_labels(group: pd.DataFrame) -> str:
        labels = []
        for row in group.sort_values("rank").head(5).itertuples(index=False):
            labels.append(f"{row.name} ({float(row.change_rate):+.2f}%)")
        return ", ".join(labels)

    leader_labels = leaders.groupby("sector").apply(_format_leader_labels)
    heatmap["leader_labels"] = heatmap["sector"].map(leader_labels).fillna("")

    _cr = pd.to_numeric(heatmap["top5_change_rate_mean"], errors="coerce").fillna(0.0)
    _tv = heatmap["total_trading_value"]
    _tv_q75 = float(_tv.quantile(0.75)) if len(_tv) > 1 else 0.0
    heatmap["badges"] = [
        ",".join(b for b in (
            "급등" if _cr.iat[i] >= 10.0 else "",
            "거래대금 TOP" if _tv_q75 > 0 and float(_tv.iat[i]) >= _tv_q75 else "",
        ) if b)
        for i in range(len(heatmap))
    ]

    return heatmap[THEME_HEATMAP_COLUMNS].reset_index(drop=True)


def _build_leader_view(leaders: pd.DataFrame) -> pd.DataFrame:
    if leaders.empty:
        return _empty_dataframe(THEME_LEADER_COLUMNS)
    view = leaders.copy()
    view["theme_id"] = view["sector"].astype(str)
    view["theme_name"] = view["sector"].astype(str)
    return view[THEME_LEADER_COLUMNS].reset_index(drop=True)


def get_morning_board_view_models(
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Return summary, ranked themes, and sector leader rows from one API snapshot."""

    settings, theme_map, prices, sectors, leaders, error_message, effective_mock = _load_ranked_snapshot(
        on_progress=on_progress
    )
    summary = _build_market_summary(settings, theme_map, prices, sectors, error_message, effective_mock)
    heatmap = _build_theme_heatmap(sectors, leaders)
    leader_view = _build_leader_view(leaders)
    return summary, heatmap, leader_view


def get_market_summary() -> dict[str, Any]:
    """Return stable market/theme summary values for Streamlit view models."""

    settings, theme_map, prices, sectors, _leaders, error_message, effective_mock = _load_ranked_snapshot()
    return _build_market_summary(settings, theme_map, prices, sectors, error_message, effective_mock)


def get_market_movers(date: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Return mock Korean market mover candidates sorted by pct_change desc.

    The date argument is reserved for the future real-data implementation.
    """

    del date
    try:
        normalized_limit = max(0, int(limit))
    except (TypeError, ValueError):
        normalized_limit = 30

    movers = sorted(
        MOCK_MARKET_MOVERS,
        key=lambda item: float(item.get("pct_change", 0.0)),
        reverse=True,
    )
    return [
        {key: mover[key] for key in MARKET_MOVER_KEYS}
        for mover in movers[:normalized_limit]
    ]


def get_theme_heatmap() -> pd.DataFrame:
    """Return one stable row per theme/sector for future Streamlit or Plotly rendering."""

    _settings, _theme_map, _prices, sectors, leaders, _error_message, _effective_mock = _load_ranked_snapshot()
    return _build_theme_heatmap(sectors, leaders)


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

    return _build_leader_view(selected)

