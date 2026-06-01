from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.universe_builder import (
    UNIVERSE_COLUMNS,
    UniverseBuildConfig,
    build_universe,
    config_from_settings,
    normalize_krx_frame,
)


def _theme_map() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"code": "005930", "name": "삼성전자", "theme1": "반도체", "theme2": "AI", "theme3": ""},
            {"code": "000660", "name": "SK하이닉스", "theme1": "반도체", "theme2": "HBM", "theme3": "메모리"},
            {"code": "123456", "name": "대형조선", "theme1": "조선", "theme2": "", "theme3": ""},
        ]
    )


def _krx_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI", "Sector": "전기전자", "Marcap": 600_000_000_000, "Amount": 200_000_000_000},
            {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI", "Sector": "전기전자", "Marcap": 700_000_000_000, "Amount": 90_000_000_000},
            {"Code": "111111", "Name": "소형주", "Market": "KOSDAQ", "Sector": "기타", "Marcap": 100_000_000_000, "Amount": 300_000_000_000},
            {"Code": "222222", "Name": "저거래대금", "Market": "KOSPI", "Sector": "기타", "Marcap": 800_000_000_000, "Amount": 10_000_000_000},
            {"Code": "333333", "Name": "KODEX 200", "Market": "ETF", "Sector": "ETF", "Marcap": 900_000_000_000, "Amount": 400_000_000_000},
            {"Code": "444444", "Name": "미래에셋스팩1호", "Market": "KOSDAQ", "Sector": "금융 SPAC", "Marcap": 900_000_000_000, "Amount": 400_000_000_000},
            {"Code": "555555", "Name": "삼성전자우", "Market": "KOSPI", "Sector": "전기전자", "Marcap": 900_000_000_000, "Amount": 400_000_000_000},
            {"Code": "666666", "Name": "관리종목테스트", "Market": "KOSDAQ", "Sector": "관리종목", "Marcap": 900_000_000_000, "Amount": 400_000_000_000},
        ]
    )


def test_config_from_settings_reads_universe_defaults() -> None:
    config = config_from_settings()

    assert config.min_market_cap == 500_000_000_000
    assert config.min_trade_value == 0
    assert config.exclude_etf is True
    assert config.exclude_spac is True
    assert config.exclude_preferred is True
    assert config.exclude_managed is True
    assert config.max_codes == 300


def test_normalize_krx_frame_accepts_project_and_fdr_column_names() -> None:
    normalized = normalize_krx_frame(_krx_rows())

    assert list(normalized["code"].head(2)) == ["005930", "000660"]
    assert normalized.loc[normalized["code"] == "005930", "market_cap"].iloc[0] == 600_000_000_000
    assert normalized.loc[normalized["code"] == "005930", "trade_value"].iloc[0] == 200_000_000_000
    assert bool(normalized.loc[normalized["code"] == "333333", "is_etf"].iloc[0]) is True
    assert bool(normalized.loc[normalized["code"] == "444444", "is_spac"].iloc[0]) is True
    assert bool(normalized.loc[normalized["code"] == "555555", "is_preferred"].iloc[0]) is True
    assert bool(normalized.loc[normalized["code"] == "666666", "is_managed"].iloc[0]) is True


def test_build_universe_applies_market_cap_trade_value_and_type_filters() -> None:
    config = UniverseBuildConfig(
        min_market_cap=500_000_000_000,
        min_trade_value=100_000_000_000,
        max_codes=300,
    )

    result = build_universe(
        _krx_rows(),
        _theme_map(),
        config,
        generated_at=datetime(2026, 6, 1, 9, 30, 0),
    )

    assert list(result.universe.columns) == UNIVERSE_COLUMNS
    assert set(result.universe["code"]) == {"005930"}
    assert result.metadata["total_count"] == 8
    assert result.metadata["selected_count"] == 1
    assert result.metadata["excluded_count"] == 7
    assert result.metadata["excluded_by_reason"] == {
        "market_cap_below_min": 1,
        "trade_value_below_min": 2,
        "etf": 1,
        "spac": 1,
        "preferred": 1,
        "managed": 1,
    }
    assert result.metadata["min_market_cap"] == 500_000_000_000
    assert result.metadata["min_trade_value"] == 100_000_000_000
    assert result.metadata["generated_at"] == "2026-06-01T09:30:00"


def test_build_universe_preserves_multi_theme_long_format() -> None:
    config = UniverseBuildConfig(
        min_market_cap=500_000_000_000,
        min_trade_value=0,
        max_codes=300,
    )

    result = build_universe(_krx_rows().head(1), _theme_map(), config)

    assert result.metadata["selected_count"] == 1
    assert result.universe["code"].tolist() == ["005930", "005930"]
    assert set(result.universe["theme"]) == {"반도체", "AI"}
    assert set(result.universe["sector"]) == {"전기전자"}
    assert set(result.universe["selected_reason"]) == {"passes_universe_filters"}
    assert set(result.universe["source"]) == {"krx"}


def test_build_universe_applies_intraday_max_codes_by_market_cap_then_trade_value() -> None:
    krx = pd.DataFrame(
        [
            {"code": "100001", "name": "A", "sector": "테마", "market": "KOSPI", "market_cap": 900, "trade_value": 10},
            {"code": "100002", "name": "B", "sector": "테마", "market": "KOSPI", "market_cap": 700, "trade_value": 90},
            {"code": "100003", "name": "C", "sector": "테마", "market": "KOSPI", "market_cap": 700, "trade_value": 50},
        ]
    )
    theme_map = pd.DataFrame(
        [
            {"code": "100001", "name": "A", "theme1": "A테마", "theme2": "", "theme3": ""},
            {"code": "100002", "name": "B", "theme1": "B테마", "theme2": "", "theme3": ""},
            {"code": "100003", "name": "C", "theme1": "C테마", "theme2": "", "theme3": ""},
        ]
    )
    config = UniverseBuildConfig(min_market_cap=0, min_trade_value=0, max_codes=2)

    result = build_universe(krx, theme_map, config)

    assert result.universe["code"].tolist() == ["100001", "100002"]
    assert result.metadata["selected_count"] == 2
    assert result.metadata["excluded_count"] == 1
    assert result.metadata["excluded_by_reason"] == {"max_codes_limit": 1}


def test_build_universe_can_disable_type_exclusions() -> None:
    config = UniverseBuildConfig(
        min_market_cap=0,
        min_trade_value=0,
        exclude_etf=False,
        exclude_spac=False,
        exclude_preferred=False,
        exclude_managed=False,
        max_codes=300,
    )

    result = build_universe(_krx_rows(), _theme_map(), config)

    assert {"333333", "444444", "555555", "666666"}.issubset(set(result.universe["code"]))
    assert result.metadata["excluded_by_reason"] == {}
