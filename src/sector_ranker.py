from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .dummy_data import REQUIRED_PRICE_COLUMNS
from .theme_loader import themes_to_long

_KRX_REQUIRED_COLUMNS = frozenset(
    ["code", "name", "sector", "change_rate", "trade_value", "volume", "open_price", "current_price"]
)

INTRADAY_THEME_LIMIT = 5
INTRADAY_LEADER_LIMIT = 5
INTRADAY_LEADER_MIN_LIMIT = 3


@dataclass(frozen=True)
class IntradayRankingWeights:
    leader_change_rank: float = 0.40
    leader_trade_rank: float = 0.30
    leader_open_strength: float = 0.15
    leader_trade_contribution: float = 0.10
    leader_surge: float = 0.05
    theme_top_change: float = 0.28
    theme_trade_value: float = 0.22
    theme_excess_return: float = 0.18
    theme_rising_ratio: float = 0.17
    theme_trade_concentration: float = 0.08
    theme_stability: float = 0.07


DEFAULT_INTRADAY_WEIGHTS = IntradayRankingWeights()


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


def rank_sectors_krx(prices: pd.DataFrame, top_n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """KRX 전체 종목 데이터로 섹터 랭킹 계산.

    prices 에는 이미 'sector' 컬럼이 있어야 한다 (theme_map 불필요).
    반환 스키마는 rank_sectors() 와 동일.
    """
    missing = _KRX_REQUIRED_COLUMNS - set(prices.columns)
    if missing:
        raise ValueError(f"KRX price data missing columns: {sorted(missing)}")

    df = prices.copy()
    for col in ("change_rate", "trade_value", "volume", "open_price", "current_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    open_nonzero = df["open_price"].replace(0, pd.NA)
    df["open_to_current_strength"] = (
        (df["current_price"] - df["open_price"]) / open_nonzero * 10.0
    ).fillna(0.0)
    df["theme_representative_score"] = 1.0

    df["change_rate_rank_score"] = df.groupby("sector")["change_rate"].transform(_rank_score)
    df["trade_value_rank_score"] = df.groupby("sector")["trade_value"].transform(_rank_score)
    df["leader_score"] = (
        df["change_rate_rank_score"] * 0.45
        + df["trade_value_rank_score"] * 0.35
        + df["open_to_current_strength"] * 0.10
        + df["theme_representative_score"] * 0.10
    )

    sector_rows = []
    leader_rows = []
    for sector, group in df.groupby("sector", sort=False):
        if group.empty:
            continue
        top_by_change = group.nlargest(min(top_n, len(group)), "change_rate")
        leaders = group.sort_values(
            ["leader_score", "change_rate", "trade_value"],
            ascending=[False, False, False],
        ).head(top_n)
        sector_rows.append(
            {
                "sector": sector,
                "top5_change_rate_mean": float(top_by_change["change_rate"].mean()),
                "trade_value_sum": float(group["trade_value"].sum()),
                "rising_ratio": float((group["change_rate"] > 0).mean()),
                "limit_up_count": int((group["change_rate"] >= 29.5).sum()),
                "stock_count": len(group),
            }
        )
        leader_rows.append(leaders.assign(rank=range(1, len(leaders) + 1)))

    if not sector_rows:
        return pd.DataFrame(), pd.DataFrame()

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

    leaders_df = pd.concat(leader_rows, ignore_index=True)
    leaders_df["rank"] = leaders_df["rank"].astype(int)
    return sectors, leaders_df


def rank_intraday_leaders(
    quotes: pd.DataFrame,
    universe: pd.DataFrame,
    previous_snapshot: dict[str, Any] | None = None,
    previous_rank_state: dict[str, Any] | None = None,
    *,
    theme_limit: int = INTRADAY_THEME_LIMIT,
    leader_limit: int = INTRADAY_LEADER_LIMIT,
    weights: IntradayRankingWeights = DEFAULT_INTRADAY_WEIGHTS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Rank intraday leading themes and leaders from quote + universe frames.

    Existing morning-board ranking functions are intentionally untouched. This
    function returns JSON-ready dictionaries for a future intraday snapshot.
    """
    frame = _build_intraday_frame(quotes, universe)
    now = generated_at or datetime.now()
    if frame.empty:
        return {
            "summary": _intraday_summary(frame, pd.DataFrame(), now),
            "themes": [],
            "leaders": [],
            "rank_events": [],
            "provider_status": _provider_status(quotes, universe, frame, now),
        }

    scored = _add_intraday_leader_scores(frame, weights)
    themes_df, leaders_df = _rank_intraday_theme_frames(
        scored,
        previous_snapshot=previous_snapshot,
        previous_rank_state=previous_rank_state,
        theme_limit=max(1, int(theme_limit)),
        leader_limit=max(INTRADAY_LEADER_MIN_LIMIT, int(leader_limit)),
        weights=weights,
    )
    rank_events = _build_rank_events(
        _extract_previous_ranks(previous_snapshot, previous_rank_state),
        themes_df,
        limit=max(1, int(theme_limit)),
    )
    return {
        "summary": _intraday_summary(scored, themes_df, now),
        "themes": _records(themes_df),
        "leaders": _records(leaders_df),
        "rank_events": rank_events,
        "provider_status": _provider_status(quotes, universe, scored, now),
    }


def _build_intraday_frame(quotes: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if quotes.empty or universe.empty:
        return pd.DataFrame()
    quote_df = quotes.copy()
    universe_df = universe.copy()
    if "code" not in quote_df or "code" not in universe_df:
        raise ValueError("quotes and universe must both include a code column.")

    quote_df["code"] = quote_df["code"].map(_normalize_code)
    universe_df["code"] = universe_df["code"].map(_normalize_code)
    quote_df = quote_df.drop_duplicates(subset=["code"], keep="last")

    for column in ("name", "sector", "theme", "market", "source"):
        if column not in universe_df:
            universe_df[column] = ""
    if "theme" not in universe_df or universe_df["theme"].fillna("").astype(str).str.strip().eq("").all():
        universe_df["theme"] = universe_df.get("sector", "기타")

    merged = universe_df.merge(quote_df, on="code", how="inner", suffixes=("_universe", "_quote"))
    if merged.empty:
        return pd.DataFrame()

    merged["name"] = _prefer_text(merged, "name_quote", "name_universe", "code")
    merged["sector"] = _prefer_text(merged, "sector", default="기타")
    merged["theme"] = _prefer_text(merged, "theme", "sector", default="기타")
    merged["market"] = _prefer_text(merged, "market", default="")
    merged["source"] = _prefer_text(merged, "source", default="")

    for column in (
        "current_price",
        "open_price",
        "prev_close",
        "change_rate",
        "volume",
        "trade_value",
        "accumulated_trade_value",
        "minute_trade_value",
        "market_cap",
    ):
        if column not in merged:
            merged[column] = 0.0
        merged[column] = _to_numeric(merged[column])

    merged["effective_trade_value"] = merged["accumulated_trade_value"]
    missing_trade = merged["effective_trade_value"] <= 0
    merged.loc[missing_trade, "effective_trade_value"] = merged.loc[missing_trade, "trade_value"]
    fallback_trade = (merged["effective_trade_value"] <= 0) & (merged["current_price"] > 0) & (merged["volume"] > 0)
    merged.loc[fallback_trade, "effective_trade_value"] = (
        merged.loc[fallback_trade, "current_price"] * merged.loc[fallback_trade, "volume"]
    )

    missing_change = merged["change_rate"].isna() | (merged["change_rate"] == 0)
    prev_close = merged["prev_close"].replace(0, pd.NA)
    computed_change = ((merged["current_price"] - merged["prev_close"]) / prev_close * 100.0).fillna(0.0)
    merged.loc[missing_change, "change_rate"] = computed_change.loc[missing_change]

    open_price = merged["open_price"].replace(0, pd.NA)
    merged["open_to_current_strength"] = (
        (merged["current_price"] - merged["open_price"]) / open_price * 100.0
    ).fillna(0.0)
    return merged


def _add_intraday_leader_scores(
    frame: pd.DataFrame,
    weights: IntradayRankingWeights,
) -> pd.DataFrame:
    scored = frame.copy()
    scored["change_rate_rank_score"] = _rank_score(scored["change_rate"])
    scored["trade_value_rank_score"] = _rank_score(scored["effective_trade_value"])
    scored["open_strength_score"] = _min_max_to_10(scored["open_to_current_strength"])
    theme_trade_sum = scored.groupby("theme")["effective_trade_value"].transform("sum").replace(0, pd.NA)
    scored["trade_contribution_score"] = (
        scored["effective_trade_value"] / theme_trade_sum * 10.0
    ).fillna(0.0).clip(0.0, 10.0)
    minute_score = _rank_score(scored["minute_trade_value"])
    positive_momentum = (scored["change_rate"] > 0).astype(float)
    scored["surge_score"] = minute_score * positive_momentum
    scored["leader_score"] = (
        scored["change_rate_rank_score"] * weights.leader_change_rank
        + scored["trade_value_rank_score"] * weights.leader_trade_rank
        + scored["open_strength_score"] * weights.leader_open_strength
        + scored["trade_contribution_score"] * weights.leader_trade_contribution
        + scored["surge_score"] * weights.leader_surge
    )
    return scored


def _rank_intraday_theme_frames(
    scored: pd.DataFrame,
    previous_snapshot: dict[str, Any] | None,
    previous_rank_state: dict[str, Any] | None,
    theme_limit: int,
    leader_limit: int,
    weights: IntradayRankingWeights,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate_avg = float(scored["change_rate"].mean()) if not scored.empty else 0.0
    previous_ranks = _extract_previous_ranks(previous_snapshot, previous_rank_state)
    theme_rows: list[dict[str, Any]] = []
    leader_rows: list[pd.DataFrame] = []

    for theme, group in scored.groupby("theme", sort=False):
        leaders = group.sort_values(
            ["leader_score", "change_rate", "effective_trade_value"],
            ascending=[False, False, False],
        ).head(max(INTRADAY_LEADER_MIN_LIMIT, min(leader_limit, len(group))))
        top_change_mean = float(leaders["change_rate"].mean()) if not leaders.empty else 0.0
        total_trade = float(group["effective_trade_value"].sum())
        top_trade = float(leaders["effective_trade_value"].sum()) if not leaders.empty else 0.0
        concentration = top_trade / total_trade if total_trade > 0 else 0.0
        top1_share = float(leaders["effective_trade_value"].iloc[0] / total_trade) if total_trade > 0 and not leaders.empty else 0.0
        concentration_score = max(0.0, min(10.0, concentration * 10.0 - max(0.0, top1_share - 0.70) * 10.0))
        stock_count = int(group["code"].nunique())
        rising_ratio = float((group["change_rate"] > 0).mean()) if len(group) else 0.0
        participation_score = rising_ratio * min(1.0, stock_count / 3.0) * 10.0
        stability_score = _stability_score(str(theme), previous_ranks)

        ranked = leaders.assign(
            rank=range(1, len(leaders) + 1),
            theme_id=str(theme),
            theme_name=str(theme),
            trade_value=leaders["effective_trade_value"],
        )
        leader_rows.append(ranked)
        theme_rows.append(
            {
                "theme_id": str(theme),
                "theme_name": str(theme),
                "sector": _dominant_text(group["sector"]),
                "stock_count": stock_count,
                "top_leader_change_rate_mean": top_change_mean,
                "total_trading_value": total_trade,
                "rising_ratio": rising_ratio,
                "excess_return": float(group["change_rate"].mean() - candidate_avg),
                "trade_concentration": concentration,
                "trade_concentration_score": concentration_score,
                "participation_score": participation_score,
                "stability_score": stability_score,
            }
        )

    themes = pd.DataFrame(theme_rows)
    if themes.empty:
        return pd.DataFrame(), pd.DataFrame()
    themes["top_change_score"] = _rank_score(themes["top_leader_change_rate_mean"])
    themes["trade_value_score"] = _rank_score(themes["total_trading_value"])
    themes["excess_return_score"] = _rank_score(themes["excess_return"])
    themes["rising_ratio_score"] = themes["participation_score"]
    themes["theme_score"] = (
        themes["top_change_score"] * weights.theme_top_change
        + themes["trade_value_score"] * weights.theme_trade_value
        + themes["excess_return_score"] * weights.theme_excess_return
        + themes["rising_ratio_score"] * weights.theme_rising_ratio
        + themes["trade_concentration_score"] * weights.theme_trade_concentration
        + themes["stability_score"] * weights.theme_stability
    )
    themes = themes.sort_values(
        ["theme_score", "total_trading_value", "top_leader_change_rate_mean"],
        ascending=[False, False, False],
    ).head(theme_limit).reset_index(drop=True)
    themes["rank"] = range(1, len(themes) + 1)

    top_theme_ids = set(themes["theme_id"])
    leaders = pd.concat(leader_rows, ignore_index=True) if leader_rows else pd.DataFrame()
    if leaders.empty:
        return themes, leaders
    leaders = leaders[leaders["theme_id"].isin(top_theme_ids)].copy()
    keep_columns = [
        "rank",
        "theme_id",
        "theme_name",
        "sector",
        "code",
        "name",
        "current_price",
        "open_price",
        "prev_close",
        "change_rate",
        "volume",
        "trade_value",
        "minute_trade_value",
        "leader_score",
    ]
    for column in keep_columns:
        if column not in leaders:
            leaders[column] = None
    return themes, leaders[keep_columns].sort_values(["theme_id", "rank"]).reset_index(drop=True)


def _build_rank_events(
    previous_ranks: dict[str, int],
    current_themes: pd.DataFrame,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if current_themes.empty:
        return []
    current = {str(row.theme_name): int(row.rank) for row in current_themes.itertuples(index=False)}
    events: list[dict[str, Any]] = []
    for theme, rank in current.items():
        if theme not in previous_ranks:
            events.append({"event_type": "new_entry", "theme_name": theme, "current_rank": rank})
            continue
        previous_rank = previous_ranks[theme]
        if previous_rank > rank:
            events.append({
                "event_type": "rank_up",
                "theme_name": theme,
                "previous_rank": previous_rank,
                "current_rank": rank,
                "rank_delta": previous_rank - rank,
            })
        elif previous_rank < rank:
            events.append({
                "event_type": "rank_down",
                "theme_name": theme,
                "previous_rank": previous_rank,
                "current_rank": rank,
                "rank_delta": previous_rank - rank,
            })
    for theme, previous_rank in previous_ranks.items():
        if previous_rank <= limit and theme not in current:
            events.append({"event_type": "dropped", "theme_name": theme, "previous_rank": previous_rank})
    return events


def _extract_previous_ranks(
    previous_snapshot: dict[str, Any] | None,
    previous_rank_state: dict[str, Any] | None,
) -> dict[str, int]:
    source = previous_rank_state or previous_snapshot or {}
    if not isinstance(source, dict):
        return {}
    if isinstance(source.get("theme_ranks"), dict):
        return {str(k): int(v) for k, v in source["theme_ranks"].items()}
    themes = source.get("themes", [])
    if not isinstance(themes, list):
        return {}
    ranks: dict[str, int] = {}
    for index, row in enumerate(themes, start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("theme_name") or row.get("theme") or row.get("theme_id") or "").strip()
        if not name:
            continue
        try:
            rank = int(row.get("rank") or index)
        except (TypeError, ValueError):
            rank = index
        ranks[name] = rank
    return ranks


def _intraday_summary(frame: pd.DataFrame, themes: pd.DataFrame, generated_at: datetime) -> dict[str, Any]:
    top = themes.iloc[0] if not themes.empty else None
    return {
        "board_type": "intraday_leader_board",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "theme_count": int(themes["theme_id"].nunique()) if not themes.empty else 0,
        "stock_count": int(frame["code"].nunique()) if not frame.empty and "code" in frame else 0,
        "top_theme": None if top is None else str(top["theme_name"]),
        "top_theme_score": None if top is None else float(top["theme_score"]),
        "avg_change_rate": float(frame["change_rate"].mean()) if not frame.empty else 0.0,
        "rising_ratio": float((frame["change_rate"] > 0).mean()) if not frame.empty else 0.0,
        "total_trade_value": float(frame["effective_trade_value"].sum()) if not frame.empty else 0.0,
    }


def _provider_status(
    quotes: pd.DataFrame,
    universe: pd.DataFrame,
    matched: pd.DataFrame,
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "mode": "intraday_snapshot",
        "quote_count": int(quotes["code"].nunique()) if not quotes.empty and "code" in quotes else 0,
        "universe_count": int(universe["code"].nunique()) if not universe.empty and "code" in universe else 0,
        "matched_count": int(matched["code"].nunique()) if not matched.empty and "code" in matched else 0,
        "updated_at": generated_at.isoformat(timespec="seconds"),
    }


def _stability_score(theme: str, previous_ranks: dict[str, int]) -> float:
    previous_rank = previous_ranks.get(theme)
    if previous_rank is None:
        return 0.0
    return max(0.0, 10.0 - max(0, previous_rank - 1) * 1.5)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    safe = frame.copy()
    for column in safe.columns:
        if pd.api.types.is_numeric_dtype(safe[column]):
            safe[column] = safe[column].astype(float)
    return safe.where(pd.notna(safe), None).to_dict(orient="records")


def _to_numeric(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.replace("+", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def _normalize_code(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _prefer_text(frame: pd.DataFrame, *columns: str, default: str = "") -> pd.Series:
    result = pd.Series("", index=frame.index, dtype="object")
    for column in columns:
        if column not in frame:
            continue
        values = frame[column].fillna("").astype(str).str.strip()
        result = result.mask(result.astype(str).str.strip() == "", values)
    return result.replace("", default)


def _dominant_text(series: pd.Series) -> str:
    values = series.fillna("").astype(str)
    values = values[values.str.strip() != ""]
    if values.empty:
        return ""
    return str(values.mode().iloc[0])
