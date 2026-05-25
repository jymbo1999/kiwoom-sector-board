from __future__ import annotations

import pandas as pd

from src.market_data import (
    MARKET_SUMMARY_KEYS,
    THEME_HEATMAP_COLUMNS,
    THEME_LEADER_COLUMNS,
    THEME_TIMELINE_COLUMNS,
    get_market_summary,
    get_theme_heatmap,
    get_theme_leaders,
    get_theme_timeline,
)


def test_get_market_summary_returns_required_keys(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    summary = get_market_summary()

    assert list(summary.keys()) == MARKET_SUMMARY_KEYS
    assert summary["effective_mock"] is True
    assert summary["data_mode"] == "mock"
    assert summary["theme_count"] > 0
    assert summary["stock_count"] > 0


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


def test_get_theme_timeline_returns_stable_schema_without_real_history() -> None:
    timeline = get_theme_timeline(days=5)

    assert list(timeline.columns) == THEME_TIMELINE_COLUMNS
    assert timeline.empty or timeline["is_dummy_timeline"].eq(True).all()
