from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

import pandas as pd

from .config import Settings, load_settings
from .theme_loader import themes_to_long


UNIVERSE_COLUMNS = [
    "code",
    "name",
    "sector",
    "theme",
    "market",
    "market_cap",
    "trade_value",
    "is_etf",
    "is_spac",
    "is_preferred",
    "is_managed",
    "source",
    "selected_reason",
]

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "code": ("code", "Code", "종목코드", "단축코드", "ticker", "Ticker"),
    "name": ("name", "Name", "종목명", "한글 종목명", "stock_name"),
    "sector": ("sector", "Sector", "업종", "업종명", "Industry"),
    "market": ("market", "Market", "시장구분", "시장", "mkt"),
    "market_cap": ("market_cap", "MarketCap", "Marcap", "시가총액", "상장시가총액"),
    "trade_value": ("trade_value", "Amount", "거래대금", "acc_trade_value", "trading_value"),
    "is_etf": ("is_etf", "ETF", "etf"),
    "is_spac": ("is_spac", "SPAC", "spac"),
    "is_preferred": ("is_preferred", "Preferred", "preferred", "우선주"),
    "is_managed": ("is_managed", "Managed", "managed", "관리종목", "관리"),
}

_PREFERRED_RE = re.compile(r"(?:우B?|우\(전환\)|우선주)$")


@dataclass(frozen=True)
class UniverseBuildConfig:
    min_market_cap: int = 500_000_000_000
    min_trade_value: int = 0
    exclude_etf: bool = True
    exclude_spac: bool = True
    exclude_preferred: bool = True
    exclude_managed: bool = True
    max_codes: int = 300


@dataclass(frozen=True)
class UniverseBuildResult:
    universe: pd.DataFrame
    metadata: dict[str, Any]


def config_from_settings(settings: Settings | None = None) -> UniverseBuildConfig:
    active = settings or load_settings()
    return UniverseBuildConfig(
        min_market_cap=active.universe_min_market_cap,
        min_trade_value=active.universe_min_trade_value,
        exclude_etf=active.universe_exclude_etf,
        exclude_spac=active.universe_exclude_spac,
        exclude_preferred=active.universe_exclude_preferred,
        exclude_managed=active.universe_exclude_managed,
        max_codes=active.intraday_max_codes,
    )


def build_universe(
    krx_data: pd.DataFrame,
    theme_map: pd.DataFrame,
    config: UniverseBuildConfig | None = None,
    *,
    generated_at: datetime | None = None,
) -> UniverseBuildResult:
    """Build an intraday watch universe without touching ranking or delivery.

    The returned DataFrame preserves multi-theme membership in long format:
    one stock can appear in multiple rows with different `theme` values.
    Metadata counts are based on unique stock codes, not long-format rows.
    """
    active_config = config or config_from_settings()
    normalized = normalize_krx_frame(krx_data)
    if normalized.empty:
        return UniverseBuildResult(
            universe=_empty_universe_frame(),
            metadata=_metadata(
                normalized,
                pd.Series(dtype=object),
                {},
                active_config,
                generated_at,
            ),
        )

    normalized = normalized.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    exclusions = _build_exclusion_flags(normalized, active_config)
    excluded_mask = exclusions.any(axis=1) if not exclusions.empty else pd.Series(False, index=normalized.index)

    selected = normalized.loc[~excluded_mask].copy()
    eligible_count = int(selected["code"].nunique())
    max_code_excluded = 0
    if active_config.max_codes > 0:
        selected = selected.sort_values(["market_cap", "trade_value", "code"], ascending=[False, False, True])
        selected = selected.head(active_config.max_codes).copy()
        max_code_excluded = max(0, eligible_count - int(selected["code"].nunique()))

    universe = _attach_themes(selected, theme_map)
    universe["source"] = "krx"
    universe["selected_reason"] = "passes_universe_filters"
    universe = universe[UNIVERSE_COLUMNS].reset_index(drop=True)

    return UniverseBuildResult(
        universe=universe,
        metadata=_metadata(
            normalized,
            selected["code"],
            _with_max_code_exclusion(_excluded_by_reason(exclusions), max_code_excluded),
            active_config,
            generated_at,
        ),
    )


def normalize_krx_frame(krx_data: pd.DataFrame) -> pd.DataFrame:
    """Normalize likely KRX/FDR/Kiwoom column names into universe columns."""
    if krx_data.empty:
        return pd.DataFrame(columns=[c for c in UNIVERSE_COLUMNS if c not in {"theme", "source", "selected_reason"}])

    normalized = pd.DataFrame(index=krx_data.index)
    for target, aliases in _COLUMN_ALIASES.items():
        source_col = _find_column(krx_data.columns, aliases)
        if source_col is not None:
            normalized[target] = krx_data[source_col]

    if "code" not in normalized:
        raise ValueError("KRX data is missing a stock code column.")
    if "name" not in normalized:
        normalized["name"] = normalized["code"]
    if "sector" not in normalized:
        normalized["sector"] = "기타"
    if "market" not in normalized:
        normalized["market"] = ""
    if "market_cap" not in normalized:
        normalized["market_cap"] = 0
    if "trade_value" not in normalized:
        normalized["trade_value"] = 0

    normalized["code"] = normalized["code"].map(_normalize_code)
    normalized["name"] = normalized["name"].astype(str).str.strip()
    normalized["sector"] = normalized["sector"].fillna("기타").astype(str).str.strip()
    normalized.loc[normalized["sector"] == "", "sector"] = "기타"
    normalized["market"] = normalized["market"].fillna("").astype(str).str.strip()
    normalized["market_cap"] = pd.to_numeric(normalized["market_cap"], errors="coerce").fillna(0).astype("int64")
    normalized["trade_value"] = pd.to_numeric(normalized["trade_value"], errors="coerce").fillna(0).astype("int64")

    for flag in ("is_etf", "is_spac", "is_preferred", "is_managed"):
        explicit = _as_bool_series(normalized[flag], normalized.index) if flag in normalized else None
        inferred = _infer_flag(flag, normalized)
        normalized[flag] = inferred if explicit is None else (explicit | inferred)

    return normalized[
        [
            "code",
            "name",
            "sector",
            "market",
            "market_cap",
            "trade_value",
            "is_etf",
            "is_spac",
            "is_preferred",
            "is_managed",
        ]
    ].reset_index(drop=True)


def _attach_themes(selected: pd.DataFrame, theme_map: pd.DataFrame) -> pd.DataFrame:
    if selected.empty:
        return _empty_universe_frame()

    themes = themes_to_long(theme_map).rename(columns={"sector": "theme"})
    themes["code"] = themes["code"].map(_normalize_code)
    merged = selected.merge(themes[["code", "theme"]], on="code", how="left")
    merged["theme"] = merged["theme"].fillna(merged["sector"]).astype(str).str.strip()
    merged.loc[merged["theme"] == "", "theme"] = merged["sector"]
    return merged


def _build_exclusion_flags(
    normalized: pd.DataFrame,
    config: UniverseBuildConfig,
) -> pd.DataFrame:
    flags = pd.DataFrame(index=normalized.index)
    if config.min_market_cap > 0:
        flags["market_cap_below_min"] = normalized["market_cap"] < config.min_market_cap
    if config.min_trade_value > 0:
        flags["trade_value_below_min"] = normalized["trade_value"] < config.min_trade_value
    if config.exclude_etf:
        flags["etf"] = normalized["is_etf"]
    if config.exclude_spac:
        flags["spac"] = normalized["is_spac"]
    if config.exclude_preferred:
        flags["preferred"] = normalized["is_preferred"]
    if config.exclude_managed:
        flags["managed"] = normalized["is_managed"]
    return flags.fillna(False)


def _excluded_by_reason(flags: pd.DataFrame) -> dict[str, int]:
    if flags.empty:
        return {}
    return {reason: int(flags[reason].sum()) for reason in flags.columns if int(flags[reason].sum()) > 0}


def _with_max_code_exclusion(reasons: dict[str, int], count: int) -> dict[str, int]:
    if count > 0:
        updated = dict(reasons)
        updated["max_codes_limit"] = int(count)
        return updated
    return reasons


def _metadata(
    normalized: pd.DataFrame,
    selected_codes: pd.Series,
    excluded_by_reason: Mapping[str, int],
    config: UniverseBuildConfig,
    generated_at: datetime | None,
) -> dict[str, Any]:
    total_count = int(normalized["code"].nunique()) if "code" in normalized else 0
    selected_count = int(pd.Series(selected_codes).dropna().astype(str).nunique())
    return {
        "total_count": total_count,
        "selected_count": selected_count,
        "excluded_count": max(0, total_count - selected_count),
        "excluded_by_reason": dict(excluded_by_reason),
        "min_market_cap": int(config.min_market_cap),
        "min_trade_value": int(config.min_trade_value),
        "generated_at": (generated_at or datetime.now()).isoformat(timespec="seconds"),
    }


def _find_column(columns: pd.Index, aliases: tuple[str, ...]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in columns}
    for alias in aliases:
        matched = lookup.get(alias.strip().lower())
        if matched is not None:
            return matched
    return None


def _normalize_code(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _as_bool_series(values: pd.Series, index: pd.Index) -> pd.Series:
    truthy = {"1", "true", "t", "yes", "y", "on", "관리", "관리종목", "etf", "spac", "스팩", "우선주"}
    falsy = {"0", "false", "f", "no", "n", "off", "", "nan", "none"}

    def _coerce(value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in truthy:
            return True
        if text in falsy:
            return False
        return False

    return values.reindex(index).map(_coerce).fillna(False).astype(bool)


def _infer_flag(flag: str, frame: pd.DataFrame) -> pd.Series:
    name = frame["name"].fillna("").astype(str)
    sector = frame["sector"].fillna("").astype(str)
    market = frame["market"].fillna("").astype(str)
    combined = (name + " " + sector + " " + market).str.upper()
    if flag == "is_etf":
        return combined.str.contains("ETF|ETN", regex=True, na=False)
    if flag == "is_spac":
        return combined.str.contains("SPAC|스팩", regex=True, na=False)
    if flag == "is_preferred":
        return name.str.contains(_PREFERRED_RE, regex=True, na=False)
    if flag == "is_managed":
        return combined.str.contains("관리종목|MANAGED", regex=True, na=False)
    return pd.Series(False, index=frame.index)


def _empty_universe_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIVERSE_COLUMNS)
