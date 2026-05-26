from __future__ import annotations

import pandas as pd

from src.market_data import (
    MARKET_MOVER_KEYS,
    MARKET_SUMMARY_KEYS,
    THEME_HEATMAP_COLUMNS,
    THEME_LEADER_COLUMNS,
    THEME_TIMELINE_COLUMNS,
    compute_badges_from_history,
    get_market_movers,
    get_market_summary,
    get_theme_heatmap,
    get_theme_history,
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


def test_get_theme_timeline_returns_new_schema_with_mock_data(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    timeline = get_theme_timeline(days=5)

    assert list(timeline.columns) == THEME_TIMELINE_COLUMNS
    assert not timeline.empty
    assert len(timeline) <= 5
    assert timeline["date"].notna().all()
    assert timeline["rank_1_theme"].str.len().gt(0).all()
    assert (timeline["total_trading_value"] > 0).all()


def test_get_theme_heatmap_has_badges_column(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    heatmap = get_theme_heatmap()

    assert "badges" in heatmap.columns
    assert heatmap["badges"].notna().all()


def test_compute_badges_from_history_produces_badges_for_today_themes() -> None:
    history = get_theme_history()

    badges = compute_badges_from_history(history)

    assert isinstance(badges, dict)
    today_themes = {t["theme"] for t in history[0]["themes"]}
    assert any(t in badges for t in today_themes), "오늘 테마 중 배지가 있는 항목이 없습니다"
    for badge_list in badges.values():
        assert isinstance(badge_list, list)
        assert 1 <= len(badge_list) <= 2


def test_compute_badges_from_history_empty_input() -> None:
    assert compute_badges_from_history([]) == {}
