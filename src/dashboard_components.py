from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st


CARD_COLORS = [
    "#fff2cc",
    "#d9ead3",
    "#f4cccc",
    "#d9eaf7",
    "#eadcf8",
    "#fce5cd",
]


def _html(markup: str) -> None:
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def format_krw(value: float) -> str:
    if value >= 1_0000_0000_0000:
        return f"{value / 1_0000_0000_0000:.1f}조원"
    if value >= 1_0000_0000:
        return f"{value / 1_0000_0000:.0f}억원"
    return f"{value:,.0f}원"


def inject_board_styles() -> None:
    _html(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            max-width: 1320px;
        }
        .board-hero {
            background: linear-gradient(90deg, #c81717 0%, #f36f21 100%);
            color: #fff;
            border: 4px solid #260044;
            padding: 18px 24px;
            margin-bottom: 12px;
            box-shadow: 0 6px 0 #260044;
        }
        .board-hero h1 {
            font-size: clamp(2.3rem, 5vw, 4.6rem);
            line-height: 1;
            margin: 0;
            color: #fff;
            font-weight: 1000;
            letter-spacing: 0;
            text-shadow: 3px 3px 0 #151515;
        }
        .board-meta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin: 12px 0 18px;
        }
        .board-meta-item {
            border: 2px solid #260044;
            background: #fff;
            color: #111;
            padding: 9px 12px;
            font-weight: 800;
        }
        .sector-board {
            background: #2b0060;
            border: 4px solid #111;
            padding: 14px;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
        }
        .sector-card {
            background: var(--sector-card-bg);
            border: 3px solid #111;
            border-radius: 9px;
            color: #111;
            overflow: hidden;
            min-height: 300px;
        }
        .sector-card-header {
            background: #f1c232;
            color: #12002d;
            border-bottom: 3px solid #111;
            padding: 10px 12px;
            font-size: 1.35rem;
            font-weight: 1000;
        }
        .sector-card-body {
            padding: 12px 14px 14px;
        }
        .sector-reason {
            color: #a61c1c;
            font-weight: 800;
            margin-bottom: 8px;
            min-height: 42px;
        }
        .sector-stats {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 6px;
            margin: 8px 0 10px;
        }
        .sector-stat {
            background: rgba(255, 255, 255, 0.74);
            border: 1px solid rgba(0, 0, 0, 0.35);
            color: #111;
            padding: 7px;
            text-align: center;
            font-size: 0.82rem;
            font-weight: 800;
        }
        .sector-stat strong {
            display: block;
            color: #111;
            font-size: 1rem;
            margin-top: 2px;
        }
        .leader-list {
            list-style: none;
            margin: 0;
            padding: 0;
        }
        .leader-list li {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            border-bottom: 1px solid rgba(0, 0, 0, 0.25);
            padding: 7px 0;
            font-size: 1.02rem;
            font-weight: 850;
        }
        .leader-name {
            color: #111;
            overflow-wrap: anywhere;
        }
        .leader-rate {
            white-space: nowrap;
            font-weight: 1000;
            color: #111;
        }
        .leader-hot {
            color: #b40000;
            text-decoration: underline;
            text-decoration-thickness: 3px;
            text-decoration-color: #f1c232;
            text-underline-offset: 4px;
        }
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            font-weight: 800;
            color: #f7f7f7;
        }
        .summary-table th {
            background: #d9ead3;
            border: 2px solid #111;
            color: #111;
            padding: 8px;
            text-align: center;
        }
        .summary-table td {
            border: 1px solid #333;
            padding: 8px;
            vertical-align: top;
        }
        @media (max-width: 960px) {
            .sector-board,
            .board-meta {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """
    )


def render_header(reference_time: datetime, use_mock: bool) -> None:
    inject_board_styles()
    _html(
        """
        <div class="board-hero">
            <h1>오늘의 주도섹터</h1>
        </div>
        """
    )
    button_col, _ = st.columns([1, 5])
    if button_col.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    _html(
        f"""
        <div class="board-meta">
            <div class="board-meta-item">기준시각<br>{escape(reference_time.strftime("%Y-%m-%d %H:%M:%S"))}</div>
            <div class="board-meta-item">데이터 모드<br>{'Mock' if use_mock else 'Kiwoom REST'}</div>
            <div class="board-meta-item">화면 기준<br>09:03 / 09:15 / 10:00</div>
        </div>
        """
    )


def render_refresh_targets() -> None:
    st.caption("장 시작 후 확인 기준으로 새로고침해 섹터 강도와 대장주 후보를 비교합니다.")


def _sector_reason(row: pd.Series) -> str:
    rising = row["rising_ratio"] * 100
    return (
        f"상승종목 {rising:.0f}% · 거래대금 {format_krw(float(row['trade_value_sum']))} "
        f"· 점수 {row['sector_score']:.2f}"
    )


def _render_sector_card_html(row: pd.Series, sector_leaders: pd.DataFrame, bg_color: str) -> str:
    leader_items = []
    for leader in sector_leaders.sort_values("rank").itertuples(index=False):
        hot_class = " leader-hot" if leader.change_rate >= 7 else ""
        leader_items.append(
            "<li>"
            f"<span class=\"leader-name\">{int(leader.rank)}. {escape(str(leader.name))} "
            f"<small>({escape(str(leader.code))})</small></span>"
            f"<span class=\"leader-rate{hot_class}\">{leader.change_rate:+.2f}%</span>"
            "</li>"
        )

    return (
        f'<article class="sector-card" style="--sector-card-bg: {bg_color};">'
        f'<div class="sector-card-header">{escape(str(row["sector"]))}</div>'
        '<div class="sector-card-body">'
        f'<div class="sector-reason">{escape(_sector_reason(row))}</div>'
        '<div class="sector-stats">'
        f'<div class="sector-stat">점수<strong>{row["sector_score"]:.2f}</strong></div>'
        f'<div class="sector-stat">상승비율<strong>{row["rising_ratio"] * 100:.0f}%</strong></div>'
        f'<div class="sector-stat">종목수<strong>{int(row["stock_count"])}</strong></div>'
        "</div>"
        f'<ul class="leader-list">{"".join(leader_items)}</ul>'
        "</div>"
        "</article>"
    )


def render_sector_cards(sectors: pd.DataFrame, leaders: pd.DataFrame, limit: int = 6) -> None:
    top_sectors = sectors.head(limit)
    cards = []
    for index, row in top_sectors.iterrows():
        sector_leaders = leaders[leaders["sector"] == row["sector"]]
        cards.append(_render_sector_card_html(row, sector_leaders, CARD_COLORS[index % len(CARD_COLORS)]))
    _html(f'<section class="sector-board">{"".join(cards)}</section>')


def render_summary_table(sectors: pd.DataFrame, leaders: pd.DataFrame, limit: int = 12) -> None:
    rows = []
    for rank, row in enumerate(sectors.head(limit).itertuples(index=False), start=1):
        sector_leaders = leaders[leaders["sector"] == row.sector].sort_values("rank").head(3)
        names = "<br>".join(
            f"{escape(str(leader.name))} ({leader.change_rate:+.2f}%)"
            for leader in sector_leaders.itertuples(index=False)
        )
        rows.append(
            "<tr>"
            f"<td>{rank}</td>"
            f"<td><strong>{escape(str(row.sector))}</strong></td>"
            f"<td>{row.sector_score:.2f}</td>"
            f"<td>{row.rising_ratio * 100:.0f}%</td>"
            f"<td>{format_krw(float(row.trade_value_sum))}</td>"
            f"<td>{names}</td>"
            "</tr>"
        )
    _html(
        """
        <table class="summary-table">
            <thead>
                <tr>
                    <th>순위</th>
                    <th>섹터</th>
                    <th>점수</th>
                    <th>상승비율</th>
                    <th>거래대금</th>
                    <th>대표 종목</th>
                </tr>
            </thead>
            <tbody>
        """
        + "".join(rows)
        + """
            </tbody>
        </table>
        """
    )
