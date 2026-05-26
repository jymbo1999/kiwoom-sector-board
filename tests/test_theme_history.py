from __future__ import annotations

from src.market_data import get_theme_history, get_theme_history_table, get_today_featured_themes


def test_get_theme_history_returns_list() -> None:
    result = get_theme_history()
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_theme_history_2026_05_22_has_six_sectors() -> None:
    history = get_theme_history()
    target = next((d for d in history if d["date"] == "2026-05-22"), None)
    assert target is not None, "2026-05-22 데이터가 없습니다"
    assert target["theme_count"] >= 6
    assert len(target["themes"]) >= 6


def test_get_theme_history_table_row_count_matches_total_themes() -> None:
    history = get_theme_history()
    total_themes = sum(d["theme_count"] for d in history)
    table = get_theme_history_table()
    assert len(table) == total_themes


def test_get_theme_history_table_rows_have_required_columns() -> None:
    table = get_theme_history_table()
    required = {"date", "weekday", "theme", "reason", "leader_1"}
    for row in table:
        assert required.issubset(row.keys()), f"row missing columns: {required - row.keys()}"


def test_get_theme_history_table_handles_fewer_than_five_leaders() -> None:
    table = get_theme_history_table()
    sparse = [r for r in table if r["theme"] == "개별 이슈"]
    assert len(sparse) > 0, "'개별 이슈' 테마 행이 없습니다"
    row = sparse[0]
    assert row["leader_4"] == "-"
    assert row["leader_5"] == "-"


def test_get_theme_history_table_change_values_have_percent_sign() -> None:
    table = get_theme_history_table()
    for row in table:
        for i in range(1, 6):
            val = row[f"leader_{i}"]
            if val != "-":
                assert "%" in val, f"leader_{i} 값에 % 가 없습니다: {val!r}"


def test_get_today_featured_themes_returns_at_least_six() -> None:
    themes = get_today_featured_themes()
    assert isinstance(themes, list)
    assert len(themes) >= 6


def test_get_today_featured_themes_has_required_keys() -> None:
    themes = get_today_featured_themes()
    for t in themes:
        assert "theme" in t, f"'theme' 키가 없습니다: {t}"
        assert "reason" in t, f"'reason' 키가 없습니다: {t}"
        assert "leaders" in t, f"'leaders' 키가 없습니다: {t}"
