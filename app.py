from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.config import load_settings
from src.dashboard_components import (
    render_header,
    render_market_summary,
    render_refresh_targets,
    render_sector_cards,
    render_selected_theme_leaders,
    render_summary_table,
    render_theme_timeline,
    render_theme_treemap,
)
from src.market_data import (
    get_market_summary,
    get_theme_heatmap,
    get_theme_leaders,
    get_theme_timeline,
    load_market_prices,
)
from src.sector_ranker import rank_sectors
from src.theme_loader import load_theme_map


st.set_page_config(page_title="오늘의 주도섹터", layout="wide")


@st.cache_data(ttl=60)
def load_ranked_board():
    settings = load_settings()
    theme_map = load_theme_map(settings.theme_map_path)
    codes = theme_map["code"].dropna().astype(str).drop_duplicates().tolist()
    prices, error_message, effective_mock = load_market_prices(settings, codes)
    sectors, leaders = rank_sectors(prices, theme_map, top_n=5)
    return settings, sectors, leaders, error_message, effective_mock


@st.cache_data(ttl=30)
def load_board_view_models() -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    summary = get_market_summary()
    heatmap = get_theme_heatmap()
    timeline = get_theme_timeline(days=5)
    return summary, heatmap, timeline


@st.cache_data(ttl=30)
def load_selected_leaders(theme_id: str) -> pd.DataFrame:
    return get_theme_leaders(theme_id)


def _empty_board_state(error: Exception) -> tuple[dict, pd.DataFrame, pd.DataFrame, str]:
    return (
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "market_phase": "unknown",
            "data_mode": "unavailable",
            "effective_mock": True,
            "error_message": str(error),
            "theme_count": 0,
            "stock_count": 0,
            "top_theme": None,
            "top_theme_score": None,
            "avg_change_rate": 0.0,
            "rising_ratio": 0.0,
            "total_trade_value": 0.0,
        },
        pd.DataFrame(),
        pd.DataFrame(),
        str(error),
    )


def _theme_label(heatmap: pd.DataFrame, theme_id: str) -> str:
    if heatmap.empty or "theme_id" not in heatmap or "theme_name" not in heatmap:
        return theme_id
    matched = heatmap.loc[heatmap["theme_id"].astype(str) == str(theme_id), "theme_name"]
    if matched.empty:
        return theme_id
    return str(matched.iloc[0])


def main() -> None:
    load_error = None
    try:
        summary, heatmap, timeline = load_board_view_models()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        summary, heatmap, timeline, load_error = _empty_board_state(exc)

    render_header(datetime.now(), bool(summary.get("effective_mock")))
    render_refresh_targets()

    error_message = load_error or summary.get("error_message")
    if error_message:
        st.warning(error_message)
    if summary.get("effective_mock"):
        st.info("샘플 데이터로 화면을 표시 중입니다. 투자 추천이 아닌 UI 확인용 데이터입니다.")

    render_market_summary(summary)

    theme_options = heatmap["theme_id"].astype(str).tolist() if "theme_id" in heatmap and not heatmap.empty else []
    default_theme = str(summary.get("top_theme") or theme_options[0]) if theme_options else None
    default_index = theme_options.index(default_theme) if default_theme in theme_options else 0

    chart_col, detail_col = st.columns([2, 1], gap="large")
    with chart_col:
        st.subheader("테마 흐름")
        render_theme_treemap(heatmap)
    with detail_col:
        st.subheader("선택 테마 대장주 Top 5")
        if theme_options:
            selected_theme = st.selectbox(
                "테마 선택",
                options=theme_options,
                index=default_index,
                format_func=lambda theme_id: _theme_label(heatmap, theme_id),
            )
            leaders = load_selected_leaders(selected_theme)
            render_selected_theme_leaders(leaders)
        else:
            st.info("선택 가능한 테마 데이터가 없습니다.")

    st.subheader("최근 5거래일 테마 지속성")
    render_theme_timeline(timeline)

    with st.expander("기존 카드형 섹터맵/관전표 보기", expanded=False):
        try:
            settings, sectors, leaders, legacy_error, _effective_mock = load_ranked_board()
        except (FileNotFoundError, ValueError, KeyError) as exc:
            st.warning(f"기존 섹터맵 데이터를 불러오지 못했습니다: {exc}")
        else:
            if settings.account_no:
                st.caption("계좌번호는 조회 전용 MVP에서 사용하지 않으며 화면에 표시하지 않습니다.")
            if legacy_error:
                st.warning(legacy_error)
            board_tab, table_tab = st.tabs(["카드형 섹터맵", "관전표"])
            with board_tab:
                render_sector_cards(sectors, leaders, limit=6)
            with table_tab:
                render_summary_table(sectors, leaders, limit=12)


if __name__ == "__main__":
    main()
