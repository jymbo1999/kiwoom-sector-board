from __future__ import annotations

import pandas as pd

from src.config import DATA_DIR, Settings
from src.kiwoom_auth import KiwoomAuthError
from src.market_data import (
    MARKET_MOVER_KEYS,
    MARKET_SUMMARY_KEYS,
    THEME_HEATMAP_COLUMNS,
    THEME_LEADER_COLUMNS,
    get_market_movers,
    get_market_summary,
    get_theme_heatmap,
    get_theme_leaders,
    load_market_prices,
)


def test_get_market_summary_returns_required_keys(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    summary = get_market_summary()

    assert list(summary.keys()) == MARKET_SUMMARY_KEYS
    assert summary["effective_mock"] is True
    assert summary["data_mode"] == "mock"
    assert summary["theme_count"] > 0
    assert summary["stock_count"] > 0


def test_get_market_movers_returns_limited_required_keys_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("KIWOOM_APP_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_APP_SECRET", raising=False)
    monkeypatch.delenv("KIWOOM_SECRET_KEY", raising=False)

    movers = get_market_movers(limit=5)

    assert isinstance(movers, list)
    assert len(movers) <= 5
    assert movers
    assert all(list(item.keys()) == MARKET_MOVER_KEYS for item in movers)


def test_get_market_movers_sorted_by_pct_change_desc() -> None:
    movers = get_market_movers()
    pct_changes = [item["pct_change"] for item in movers]

    assert pct_changes == sorted(pct_changes, reverse=True)


def test_get_theme_heatmap_returns_required_columns_and_mock_data(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    heatmap = get_theme_heatmap()

    assert list(heatmap.columns) == THEME_HEATMAP_COLUMNS
    assert not heatmap.empty
    assert heatmap["theme_id"].notna().all()
    assert heatmap["theme_name"].notna().all()


def test_get_theme_leaders_valid_theme_id_returns_at_most_five_rows(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")
    theme_id = str(get_theme_heatmap().iloc[0]["theme_id"])

    leaders = get_theme_leaders(theme_id)

    assert list(leaders.columns) == THEME_LEADER_COLUMNS
    assert 0 < len(leaders) <= 5
    assert set(leaders["theme_id"]) == {theme_id}
    assert leaders["rank"].tolist() == sorted(leaders["rank"].tolist())


def test_get_theme_leaders_unknown_theme_id_returns_empty_stable_frame(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    leaders = get_theme_leaders("__unknown_theme__")

    assert isinstance(leaders, pd.DataFrame)
    assert list(leaders.columns) == THEME_LEADER_COLUMNS
    assert leaders.empty


def test_get_theme_heatmap_has_badges_column(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    heatmap = get_theme_heatmap()

    assert "badges" in heatmap.columns
    assert heatmap["badges"].notna().all()


def test_load_market_prices_falls_back_when_auth_fails(monkeypatch) -> None:
    class AuthFailingClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def fetch_current_prices(self, _codes: list[str], on_progress=None) -> pd.DataFrame:
            raise KiwoomAuthError("투자구분(실전/모의)이 달라서 Appkey를 사용할수가 없습니다")

    monkeypatch.setattr("src.market_data.KiwoomRestClient", AuthFailingClient)
    settings = Settings(
        app_key="mock-key",
        secret_key="mock-secret",
        base_url="https://api.kiwoom.com",
        account_no="",
        use_mock=False,
        theme_map_path=DATA_DIR / "theme_map.csv",
        sample_prices_path=DATA_DIR / "sample_prices.csv",
    )

    prices, error_message, effective_mock = load_market_prices(settings, ["005930"])

    assert not prices.empty
    assert effective_mock is True
    assert error_message is not None
    assert "키움 API 조회에 실패" in error_message


def test_get_theme_heatmap_has_leader_labels_with_change_rates(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    heatmap = get_theme_heatmap()

    assert "leader_labels" in heatmap.columns
    assert heatmap["leader_labels"].str.contains("%", regex=False).any()


