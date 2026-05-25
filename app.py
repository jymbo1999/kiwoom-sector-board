from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.config import load_settings
from src.dashboard_components import (
    render_header,
    render_refresh_targets,
    render_sector_cards,
    render_summary_table,
)
from src.market_data import load_market_prices
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


def main() -> None:
    settings, sectors, leaders, error_message, effective_mock = load_ranked_board()
    render_header(datetime.now(), effective_mock)
    render_refresh_targets()

    if settings.account_no:
        st.caption("계좌번호는 조회 전용 MVP에서 사용하지 않으며 화면에 표시하지 않습니다.")
    if error_message:
        st.warning(error_message)
    if effective_mock:
        st.info("샘플 데이터로 화면을 표시 중입니다. 투자 추천이 아닌 UI 확인용 데이터입니다.")

    board_tab, table_tab = st.tabs(["카드형 섹터맵", "관전표"])
    with board_tab:
        render_sector_cards(sectors, leaders, limit=6)
    with table_tab:
        render_summary_table(sectors, leaders, limit=12)


if __name__ == "__main__":
    main()
