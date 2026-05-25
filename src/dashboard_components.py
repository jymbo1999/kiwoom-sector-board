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


def render_header(reference_time: datetime, use_mock: bool | None = None) -> None:
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
            <div class="board-meta-item">데이터 모드<br>{'확인 중' if use_mock is None else ('Mock' if use_mock else 'Kiwoom REST')}</div>
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



def format_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0.00%"
    return f"{float(value):+.2f}%"


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column not in frame.columns]


def render_market_summary(summary: dict) -> None:
    """Render top-level market/theme metrics from the stable view-model dict."""

    timestamp = str(summary.get("timestamp") or "-").replace("T", " ")
    market_phase = str(summary.get("market_phase") or "unknown")
    data_mode = str(summary.get("data_mode") or "unknown")

    st.caption(f"데이터 기준 시각: {timestamp} · market_phase: {market_phase} · data_mode: {data_mode}")

    metric_cols = st.columns(5)
    metric_cols[0].metric("테마 수", f"{int(summary.get('theme_count') or 0):,}")
    metric_cols[1].metric("종목 수", f"{int(summary.get('stock_count') or 0):,}")
    metric_cols[2].metric("평균 등락률", format_pct(summary.get("avg_change_rate") or 0.0))
    metric_cols[3].metric("상승 종목 비율", f"{float(summary.get('rising_ratio') or 0.0) * 100:.0f}%")
    metric_cols[4].metric("총 거래대금", format_krw(float(summary.get("total_trade_value") or 0.0)))

    top_theme = summary.get("top_theme") or "-"
    top_score = summary.get("top_theme_score")
    st.caption(f"현재 최상위 테마: {top_theme} · 점수: {'-' if top_score is None else f'{float(top_score):.2f}'}")


def _fallback_theme_table(heatmap: pd.DataFrame) -> None:
    display_columns = [
        "theme_name",
        "theme_score",
        "top5_change_rate_mean",
        "rising_ratio",
        "total_trading_value",
        "leader_names",
    ]
    available = [column for column in display_columns if column in heatmap.columns]
    table = heatmap[available].copy()
    rename_map = {
        "theme_name": "테마",
        "theme_score": "점수",
        "top5_change_rate_mean": "Top5 평균 등락률",
        "rising_ratio": "상승비율",
        "total_trading_value": "거래대금",
        "leader_names": "대표 대장주",
    }
    table = table.rename(columns=rename_map)
    if "거래대금" in table:
        table["거래대금"] = table["거래대금"].map(lambda value: format_krw(float(value or 0)))
    if "상승비율" in table:
        table["상승비율"] = table["상승비율"].map(lambda value: f"{float(value or 0) * 100:.0f}%")
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_theme_treemap(heatmap: pd.DataFrame) -> None:
    """Render a Plotly treemap when available, otherwise a safe table heatmap fallback."""

    required = ["theme_name", "total_trading_value", "top5_change_rate_mean", "leader_names"]
    if heatmap.empty:
        st.info("테마 흐름을 표시할 데이터가 없습니다.")
        return

    missing = _require_columns(heatmap, required)
    if missing:
        st.warning(f"테마 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        _fallback_theme_table(heatmap)
        return

    chart_data = heatmap.copy()
    chart_data["total_trading_value"] = pd.to_numeric(chart_data["total_trading_value"], errors="coerce").fillna(0.0)
    chart_data["top5_change_rate_mean"] = pd.to_numeric(chart_data["top5_change_rate_mean"], errors="coerce").fillna(0.0)
    chart_data["leader_preview"] = chart_data["leader_names"].astype(str).map(
        lambda names: ", ".join([name.strip() for name in names.split(",")[:2] if name.strip()])
    )
    chart_data["label"] = chart_data.apply(
        lambda row: f"{row['theme_name']}<br>{row['top5_change_rate_mean']:+.2f}%<br>{row['leader_preview']}",
        axis=1,
    )

    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.warning("Plotly가 설치되어 있지 않아 표 형태 heatmap으로 표시합니다.")
        _fallback_theme_table(chart_data)
        return

    fig = px.treemap(
        chart_data,
        path=["theme_name"],
        values="total_trading_value",
        color="top5_change_rate_mean",
        color_continuous_scale="RdBu_r",
        hover_data={
            "theme_name": True,
            "top5_change_rate_mean": ":+.2f",
            "total_trading_value": ":,.0f",
            "leader_preview": True,
        },
    )
    fig.update_traces(text=chart_data["label"], textinfo="text")
    fig.update_layout(margin=dict(t=10, l=10, r=10, b=10), height=520)
    st.plotly_chart(fig, use_container_width=True)


def render_selected_theme_leaders(leaders: pd.DataFrame) -> None:
    if leaders.empty:
        st.info("선택한 테마의 대장주 Top 5 데이터가 없습니다.")
        return

    required = ["rank", "name", "code", "change_rate", "current_price", "trade_value", "leader_score"]
    missing = _require_columns(leaders, required)
    if missing:
        st.warning(f"대장주 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        st.dataframe(leaders, use_container_width=True, hide_index=True)
        return

    display = leaders[required].copy().rename(
        columns={
            "rank": "순위",
            "name": "종목명",
            "code": "코드",
            "change_rate": "등락률",
            "current_price": "현재가",
            "trade_value": "거래대금",
            "leader_score": "대장주 점수",
        }
    )
    display["등락률"] = display["등락률"].map(format_pct)
    display["현재가"] = display["현재가"].map(lambda value: f"{float(value or 0):,.0f}원")
    display["거래대금"] = display["거래대금"].map(lambda value: format_krw(float(value or 0)))
    display["대장주 점수"] = display["대장주 점수"].map(lambda value: f"{float(value or 0):.2f}")
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_theme_timeline(timeline: pd.DataFrame) -> None:
    if timeline.empty:
        st.info("실제 최근 5거래일 테마 지속성 데이터가 아직 없습니다. 현재 MVP는 단일 스냅샷 기준으로 표시합니다.")
        return

    required = ["date", "theme_name", "sector_score", "is_dummy_timeline"]
    missing = _require_columns(timeline, required)
    if missing:
        st.warning(f"타임라인 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        st.dataframe(timeline, use_container_width=True, hide_index=True)
        return

    display = timeline[required].copy().rename(
        columns={
            "date": "일자",
            "theme_name": "테마",
            "sector_score": "점수",
            "is_dummy_timeline": "더미 여부",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    if timeline["is_dummy_timeline"].astype(bool).any():
        st.caption("타임라인은 실제 과거 데이터가 아닌 더미 표시를 포함합니다.")
