from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st




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
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@300;400;600&display=swap">
        <style>
        html, body, [class*="css"], .stMarkdown, button, .stCaption p {
            font-family: 'Source Sans Pro', sans-serif !important;
        }
        .block-container {
            padding-top: 1.6rem;
            max-width: 1320px;
        }
        /* ── Header ── */
        .board-hero {
            padding: 20px 0 18px;
            margin-bottom: 4px;
            border-bottom: solid 1px rgba(255,255,255,0.2);
        }
        .board-hero h1 {
            font-family: 'Source Sans Pro', sans-serif;
            font-size: clamp(1.75rem, 3.8vw, 2.8rem);
            font-weight: 600;
            letter-spacing: 0.25rem;
            text-transform: uppercase;
            color: #ffffff;
            margin: 0 0 4px;
            line-height: 1.2;
        }
        .board-hero p {
            color: rgba(255,255,255,0.45);
            font-size: 0.88rem;
            font-weight: 300;
            letter-spacing: 0.15rem;
            text-transform: uppercase;
            margin: 0;
        }
        /* ── Meta grid ── */
        .board-meta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin: 14px 0 18px;
        }
        .board-meta-item {
            background: rgba(255,255,255,0.06);
            border: solid 1px rgba(255,255,255,0.2);
            border-radius: 4px;
            color: rgba(255,255,255,0.55);
            padding: 11px 14px;
            font-size: 0.85rem;
            font-weight: 300;
            letter-spacing: 0.08rem;
            text-transform: uppercase;
            line-height: 1.5;
        }
        .board-meta-item strong {
            display: block;
            color: #ffffff;
            font-size: 0.98rem;
            font-weight: 600;
            margin-top: 3px;
            text-transform: none;
            letter-spacing: 0;
        }
        /* ── Sector board grid ── */
        .sector-board {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            margin-top: 8px;
        }
        /* ── Sector card ── */
        .sector-card {
            background: rgba(255,255,255,0.06);
            border: solid 1px rgba(255,255,255,0.2);
            border-radius: 4px;
            color: #ffffff;
            overflow: hidden;
        }
        .sector-card-header {
            background: rgba(255,255,255,0.1);
            border-bottom: solid 1px rgba(255,255,255,0.15);
            padding: 10px 14px;
            font-size: 0.92rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.18rem;
            color: #ffffff;
        }
        .sector-card-body {
            padding: 14px;
        }
        .sector-reason {
            color: rgba(255,255,255,0.5);
            font-weight: 300;
            font-size: 0.9rem;
            margin-bottom: 12px;
            line-height: 1.55;
            letter-spacing: 0.02rem;
        }
        /* ── Stats row ── */
        .sector-stats {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin: 0 0 12px;
        }
        .sector-stat {
            background: rgba(255,255,255,0.04);
            border: solid 1px rgba(255,255,255,0.12);
            border-radius: 4px;
            color: rgba(255,255,255,0.5);
            padding: 7px 4px;
            text-align: center;
            font-size: 0.8rem;
            font-weight: 300;
            letter-spacing: 0.06rem;
            text-transform: uppercase;
        }
        .sector-stat strong {
            display: block;
            color: #ffffff;
            font-size: 0.98rem;
            font-weight: 600;
            margin-top: 3px;
            letter-spacing: 0;
            text-transform: none;
        }
        /* ── Leader list ── */
        .leader-list {
            list-style: none;
            margin: 0;
            padding: 0;
        }
        .leader-list li {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            border-bottom: solid 1px rgba(255,255,255,0.08);
            padding: 7px 0;
            font-size: 0.95rem;
            font-weight: 300;
        }
        .leader-list li:last-child { border-bottom: none; }
        .leader-name { color: rgba(255,255,255,0.8); overflow-wrap: anywhere; }
        .leader-rate { white-space: nowrap; font-weight: 600; color: #ffffff; }
        .leader-hot  { color: #ff7b7b; }
        /* ── Summary table ── */
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            color: #ffffff;
            font-size: 0.98rem;
        }
        .summary-table th {
            background: rgba(255,255,255,0.08);
            border-top: solid 1px rgba(255,255,255,0.25);
            border-bottom: solid 1px rgba(255,255,255,0.25);
            color: rgba(255,255,255,0.6);
            padding: 9px 12px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1rem;
            font-size: 0.82rem;
        }
        .summary-table td {
            border-bottom: solid 1px rgba(255,255,255,0.08);
            padding: 9px 12px;
            vertical-align: top;
            font-weight: 300;
        }
        .summary-table tbody tr:hover td {
            background: rgba(255,255,255,0.04);
        }
        /* ── History board table ── */
        .history-board {
            width: 100%;
            border-collapse: collapse;
            color: #ffffff;
            margin-top: 8px;
            font-size: 0.92rem;
        }
        .history-board th {
            background: rgba(255,255,255,0.08);
            border: solid 1px rgba(255,255,255,0.2);
            padding: 8px 12px;
            text-align: center;
            font-weight: 600;
            font-size: 0.82rem;
            color: rgba(255,255,255,0.55);
            letter-spacing: 0.05rem;
            text-transform: uppercase;
        }
        .history-board td {
            border: solid 1px rgba(255,255,255,0.1);
            padding: 8px 12px;
            vertical-align: top;
        }
        .history-board tbody tr:hover td {
            background: rgba(255,255,255,0.03);
        }
        .history-date {
            text-align: center;
            white-space: nowrap;
            font-weight: 600;
            color: rgba(255,255,255,0.8);
            font-size: 0.88rem;
            background: rgba(255,255,255,0.05);
        }
        .history-label {
            text-align: center;
            color: rgba(255,255,255,0.45);
            font-size: 0.82rem;
            font-weight: 400;
            white-space: nowrap;
            background: rgba(255,255,255,0.03);
        }
        .history-theme-name {
            font-weight: 600;
            color: rgba(255,255,255,0.92);
            font-size: 0.92rem;
        }
        .history-stock-list {
            margin: 0;
            padding: 0;
            list-style: none;
        }
        .history-stock-list li {
            padding: 2px 0;
            font-size: 0.88rem;
            font-weight: 300;
            color: rgba(255,255,255,0.75);
            white-space: nowrap;
        }
        .history-stock-hot {
            color: #ff7b7b;
            font-weight: 600;
        }
        @media (max-width: 960px) {
            .sector-board, .board-meta { grid-template-columns: 1fr; }
        }
        /* ── Status badges ── */
        .status-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.06rem;
            vertical-align: middle;
            margin-right: 6px;
        }
        .status-mock     { background: #f0ad4e; color: #333; }
        .status-live     { background: #27ae60; color: #fff; }
        .status-error    { background: #c0392b; color: #fff; }
        .status-fallback { background: #e67e22; color: #fff; }
        .status-delayed  { background: #3498db; color: #fff; }
        .status-unknown  { background: rgba(255,255,255,0.18); color: #fff; }
        .phase-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: 600;
            background: rgba(255,255,255,0.12);
            color: rgba(255,255,255,0.85);
            margin-right: 6px;
            letter-spacing: 0.04rem;
        }
        .status-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
            flex-wrap: wrap;
        }
        .status-bar-ts {
            color: rgba(255,255,255,0.4);
            font-size: 0.8rem;
            font-weight: 300;
            letter-spacing: 0.04rem;
        }
        .confidence-badge {
            display: inline-block;
            min-width: 72px;
            text-align: center;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.04rem;
        }
        .confidence-high { background: #27ae60; color: #ffffff; }
        .confidence-medium { background: #3498db; color: #ffffff; }
        .confidence-low { background: #e67e22; color: #ffffff; }
        .confidence-unknown { background: rgba(255,255,255,0.16); color: rgba(255,255,255,0.82); }
        .rise-reason-name {
            font-weight: 600;
            color: rgba(255,255,255,0.92);
            white-space: nowrap;
        }
        .rise-reason-code {
            color: rgba(255,255,255,0.48);
            font-size: 0.82rem;
            white-space: nowrap;
        }
        .rise-reason-summary {
            max-width: 420px;
            line-height: 1.48;
            overflow-wrap: anywhere;
        }
        .rise-reason-evidence {
            margin: 0;
            padding-left: 1rem;
            max-width: 320px;
            line-height: 1.45;
        }
        .rise-reason-evidence li {
            margin: 0 0 3px;
            overflow-wrap: anywhere;
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
            <p>Sector Board</p>
        </div>
        """
    )
    button_col, _ = st.columns([1, 7])
    if button_col.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    data_mode = "확인 중" if use_mock is None else ("Mock" if use_mock else "Kiwoom REST")
    _html(
        f"""
        <div class="board-meta">
            <div class="board-meta-item">기준 시각<strong>{escape(reference_time.strftime("%Y-%m-%d %H:%M:%S"))}</strong></div>
            <div class="board-meta-item">데이터 모드<strong>{data_mode}</strong></div>
            <div class="board-meta-item">확인 기준<strong>09:03 / 09:15 / 10:00</strong></div>
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


def _render_sector_card_html(row: pd.Series, sector_leaders: pd.DataFrame) -> str:
    leader_items = []
    for leader in sector_leaders.sort_values("rank").itertuples(index=False):
        hot_class = " leader-hot" if leader.change_rate >= 7 else ""
        leader_items.append(
            "<li>"
            f"<span class=\"leader-name\">{int(leader.rank)}. {escape(str(leader.name))} "
            f"<small style=\"opacity:.55\">({escape(str(leader.code))})</small></span>"
            f"<span class=\"leader-rate{hot_class}\">{leader.change_rate:+.2f}%</span>"
            "</li>"
        )

    return (
        '<article class="sector-card">'
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
    for _, row in top_sectors.iterrows():
        sector_leaders = leaders[leaders["sector"] == row["sector"]]
        cards.append(_render_sector_card_html(row, sector_leaders))
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


def _confidence_badge_html(confidence: str) -> str:
    value = str(confidence or "unknown").lower()
    if value not in {"high", "medium", "low", "unknown"}:
        value = "unknown"
    return f'<span class="confidence-badge confidence-{value}">{escape(value)}</span>'


def _rise_reason_rows(summaries: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        market_move = summary.get("market_move", {})
        if not isinstance(market_move, dict):
            market_move = {}
        evidence_titles = summary.get("evidence_titles", [])
        if not isinstance(evidence_titles, list):
            evidence_titles = []
        titles = [str(title) for title in evidence_titles[:3] if str(title).strip()]
        rows.append(
            {
                "name": str(summary.get("name", "")),
                "ticker": str(summary.get("ticker", "")),
                "pct_change": format_pct(market_move.get("pct_change", 0.0)),
                "sector": str(market_move.get("sector", "")),
                "reason_summary_ko": str(summary.get("reason_summary_ko", "")),
                "confidence": str(summary.get("confidence", "unknown")),
                "evidence_titles": "\n".join(titles) if titles else "-",
                "caveat": str(summary.get("caveat", "")),
            }
        )
    return rows


def render_rise_reason_summaries(summaries: list[dict]) -> None:
    """Render market mover rise-reason summaries in a stable dashboard table."""

    rows = _rise_reason_rows(summaries)
    if not rows:
        st.info("상승이유 요약을 표시할 데이터가 없습니다.")
        return

    row_html = []
    for row in rows:
        evidence_html = "-"
        if row["evidence_titles"] != "-":
            evidence_html = (
                '<ul class="rise-reason-evidence">'
                + "".join(f"<li>{escape(title)}</li>" for title in row["evidence_titles"].split("\n")[:3])
                + "</ul>"
            )
        row_html.append(
            "<tr>"
            f'<td><div class="rise-reason-name">{escape(row["name"])}</div>'
            f'<div class="rise-reason-code">{escape(row["ticker"])}</div></td>'
            f'<td>{escape(row["ticker"])}</td>'
            f'<td>{escape(row["pct_change"])}</td>'
            f'<td>{escape(row["sector"])}</td>'
            f'<td><div class="rise-reason-summary">{escape(row["reason_summary_ko"])}</div></td>'
            f'<td>{_confidence_badge_html(row["confidence"])}</td>'
            f"<td>{evidence_html}</td>"
            f'<td><div class="rise-reason-summary">{escape(row["caveat"])}</div></td>'
            "</tr>"
        )

    _html(
        """
        <div style="overflow-x:auto">
        <table class="summary-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>티커</th>
                    <th>등락률</th>
                    <th>섹터</th>
                    <th>상승이유 요약</th>
                    <th>confidence</th>
                    <th>근거 제목</th>
                    <th>주의문</th>
                </tr>
            </thead>
            <tbody>
        """
        + "".join(row_html)
        + """
            </tbody>
        </table>
        </div>
        """
    )



def format_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0.00%"
    return f"{float(value):+.2f}%"


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column not in frame.columns]


_MARKET_PHASE_KO: dict[str, str] = {
    "pre_market": "장전",
    "regular_market": "정규장",
    "after_market": "장후",
    "closed": "휴장",
}

_DATA_MODE_BADGE: dict[str, tuple[str, str, str]] = {
    # data_mode → (css_class, label, description)
    "mock":        ("status-mock",     "MOCK",     "샘플 데이터입니다. 실제 매매 판단에 사용하지 마세요."),
    "kiwoom_rest": ("status-live",     "LIVE",     "실시간 데이터"),
    "unavailable": ("status-error",    "ERROR",    "데이터 수신 오류"),
    "fallback":    ("status-fallback", "FALLBACK", "대체 데이터 사용 중"),
    "delayed":     ("status-delayed",  "DELAYED",  "지연 데이터"),
}


def _data_mode_badge_html(data_mode: str) -> str:
    css, label, desc = _DATA_MODE_BADGE.get(
        data_mode, ("status-unknown", "UNKNOWN", "알 수 없는 데이터 상태")
    )
    return (
        f'<span class="status-badge {css}" title="{escape(desc)}">'
        f'{escape(label)}</span>'
        f'<span style="color:rgba(255,255,255,0.35);font-size:0.78rem">{escape(desc)}</span>'
    )


def render_market_summary(summary: dict) -> None:
    """Render top-level market/theme metrics from the stable view-model dict."""

    timestamp = str(summary.get("timestamp") or "-").replace("T", " ")
    market_phase = str(summary.get("market_phase") or "unknown")
    data_mode = str(summary.get("data_mode") or "unknown")
    phase_ko = _MARKET_PHASE_KO.get(market_phase, market_phase)

    _html(
        f'<div class="status-bar">'
        f'{_data_mode_badge_html(data_mode)}'
        f'<span class="phase-badge">{escape(phase_ko)}</span>'
        f'<span class="status-bar-ts">데이터 기준: {escape(timestamp)}</span>'
        f'</div>'
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric("테마 수", f"{int(summary.get('theme_count') or 0):,}")
    metric_cols[1].metric("종목 수", f"{int(summary.get('stock_count') or 0):,}")
    metric_cols[2].metric("평균 등락률", format_pct(summary.get("avg_change_rate") or 0.0))
    metric_cols[3].metric("상승 종목 비율", f"{float(summary.get('rising_ratio') or 0.0) * 100:.0f}%")
    metric_cols[4].metric("총 거래대금", format_krw(float(summary.get("total_trade_value") or 0.0)))

    top_theme = summary.get("top_theme") or "-"
    top_score = summary.get("top_theme_score")
    st.caption(
        f"현재 최상위 테마: {top_theme} · 점수: "
        f"{'-' if top_score is None else f'{float(top_score):.2f}'}"
    )


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


_SIZE_BY_LABELS: dict[str, str] = {
    "total_trading_value": "테마 거래대금",
    "market_cap": "시가총액",
    "theme_score": "테마 점수",
    "equal": "동일 크기",
}


def render_theme_treemap(heatmap: pd.DataFrame, size_by: str = "total_trading_value") -> None:
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

    size_label = _SIZE_BY_LABELS.get(size_by, size_by)
    st.caption(f"박스 크기 = {size_label}  ·  색상 = 평균 등락률")

    chart_data = heatmap.copy()
    chart_data["total_trading_value"] = pd.to_numeric(chart_data["total_trading_value"], errors="coerce").fillna(0.0)
    chart_data["top5_change_rate_mean"] = pd.to_numeric(chart_data["top5_change_rate_mean"], errors="coerce").fillna(0.0)
    chart_data["leader_preview"] = chart_data["leader_names"].astype(str).map(
        lambda names: ", ".join([name.strip() for name in names.split(",")[:2] if name.strip()])
    )
    def _first_badge(badges_str: str) -> str:
        first = str(badges_str).strip().split(",")[0].strip()
        return f" [{first}]" if first else ""

    chart_data["label"] = chart_data.apply(
        lambda row: (
            f"{row['theme_name']}{_first_badge(str(row.get('badges', '')))}"
            f"<br>{row['top5_change_rate_mean']:+.2f}%"
            f"<br>{row['leader_preview']}"
        ),
        axis=1,
    )

    if size_by == "equal":
        chart_data["_size"] = 1.0
    elif size_by in chart_data.columns:
        chart_data["_size"] = pd.to_numeric(chart_data[size_by], errors="coerce").fillna(0.0).clip(lower=0.01)
    else:
        chart_data["_size"] = chart_data["total_trading_value"].clip(lower=0.01)

    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.warning("Plotly가 설치되어 있지 않아 표 형태 heatmap으로 표시합니다.")
        _fallback_theme_table(chart_data)
        return

    fig = px.treemap(
        chart_data,
        path=["theme_name"],
        values="_size",
        color="top5_change_rate_mean",
        color_continuous_scale=[(0.0, "#c0392b"), (0.5, "#2a2a2a"), (1.0, "#27ae60")],
        color_continuous_midpoint=0,
        hover_data={
            "theme_name": True,
            "top5_change_rate_mean": ":+.2f",
            "total_trading_value": ":,.0f",
            "leader_preview": True,
        },
    )
    fig.update_traces(text=chart_data["label"], textinfo="text")
    fig.update_layout(
        margin=dict(t=10, l=10, r=10, b=10),
        height=520,
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(
            tickfont=dict(color="rgba(255,255,255,0.6)"),
            title=dict(text="%", font=dict(color="rgba(255,255,255,0.6)")),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_selected_theme_leaders(leaders: pd.DataFrame) -> None:
    count = len(leaders) if not leaders.empty else 0
    st.subheader(f"선택 테마 대장주 Top {min(count, 5) if count else 5}")

    if leaders.empty:
        st.info("선택한 테마의 대장주 Top 5 데이터가 없습니다.")
        return

    # Column order: rank first, then name (most important), code, financials, score
    ordered = ["rank", "name", "code", "change_rate", "current_price", "trade_value", "leader_score"]
    missing = _require_columns(leaders, ordered)
    if missing:
        st.warning(f"대장주 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        st.dataframe(leaders, use_container_width=True, hide_index=True)
        return

    display = leaders[ordered].copy().rename(
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
    display["현재가"] = display["현재가"].map(lambda v: f"{float(v or 0):,.0f}원")
    display["거래대금"] = display["거래대금"].map(lambda v: format_krw(float(v or 0)))
    display["대장주 점수"] = display["대장주 점수"].map(lambda v: f"{float(v or 0):.2f}")

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "순위":      st.column_config.TextColumn(width="small"),
            "종목명":    st.column_config.TextColumn(width="medium"),
            "코드":      st.column_config.TextColumn(width="small"),
            "등락률":    st.column_config.TextColumn(width="small"),
            "현재가":    st.column_config.TextColumn(width="medium"),
            "거래대금":  st.column_config.TextColumn(width="medium"),
            "대장주 점수": st.column_config.TextColumn(width="small"),
        },
    )
    st.caption(
        "대장주 점수 = 등락률 순위(45%) + 거래대금 순위(35%) + 시가대비 강도(10%) + 테마 대표성(10%)"
    )


def _render_featured_theme_card_html(theme_data: dict) -> str:
    leader_items = []
    for i, leader in enumerate(theme_data.get("leaders", [])[:5], start=1):
        change = float(leader.get("change", 0))
        hot_class = " leader-hot" if change >= 7 else ""
        leader_items.append(
            "<li>"
            f"<span class=\"leader-name\">{i}. {escape(str(leader['name']))}</span>"
            f"<span class=\"leader-rate{hot_class}\">{change:+.2f}%</span>"
            "</li>"
        )
    return (
        '<article class="sector-card">'
        f'<div class="sector-card-header">{escape(str(theme_data.get("theme", "")))}</div>'
        '<div class="sector-card-body">'
        f'<div class="sector-reason">{escape(str(theme_data.get("reason", "")))}</div>'
        f'<ul class="leader-list">{"".join(leader_items)}</ul>'
        "</div>"
        "</article>"
    )


def render_featured_themes(themes: list[dict]) -> None:
    """Render today's featured sector theme cards using the existing sector-card grid CSS."""

    if not themes:
        st.info("오늘의 특징테마 데이터가 없습니다.")
        return
    cards = [_render_featured_theme_card_html(t) for t in themes]
    _html(f'<section class="sector-board">{"".join(cards)}</section>')


# 10-slot muted palette — consistent across theme names in the whole history board
_SECTOR_BG_PALETTE = [
    "rgba(100,149,237,0.13)",  # 코발트 블루
    "rgba(152,251,152,0.11)",  # 페일 그린
    "rgba(255,165,80,0.12)",   # 오렌지
    "rgba(216,130,216,0.12)",  # 라벤더
    "rgba(64,220,200,0.11)",   # 틸
    "rgba(255,215,80,0.11)",   # 골드
    "rgba(135,200,235,0.12)",  # 스카이 블루
    "rgba(240,120,120,0.11)",  # 로즈
    "rgba(180,200,100,0.11)",  # 올리브
    "rgba(190,150,240,0.12)",  # 보라
]


def _change_color(change: float) -> str:
    """Text color scaled by change rate magnitude (dark-theme friendly)."""
    if change >= 25.0:
        return "#ff4040"   # 상한가권 (29%대): 강한 빨강
    if change >= 20.0:
        return "#ff7020"   # 20-25%: 딥 오렌지
    if change >= 15.0:
        return "#ffaa33"   # 15-20%: 오렌지
    if change >= 10.0:
        return "#ffcc55"   # 10-15%: 옐로-오렌지
    if change >= 5.0:
        return "#ffe080"   # 5-10%: 연한 노랑
    if change > 0.0:
        return "rgba(255,255,255,0.72)"  # 0-5%: 기본 흰색
    if change <= -5.0:
        return "#6699ff"   # 하락: 블루
    return "rgba(255,255,255,0.45)"


def _build_sector_color_map(history: list[dict]) -> dict[str, str]:
    """Assign a consistent palette color to every unique theme name in history."""
    seen: list[str] = []
    for day in history:
        for t in day["themes"]:
            if t["theme"] not in seen:
                seen.append(t["theme"])
    return {
        name: _SECTOR_BG_PALETTE[i % len(_SECTOR_BG_PALETTE)]
        for i, name in enumerate(seen)
    }


def _render_history_board_html(history: list[dict]) -> str:
    """Build the 2-row-per-date HTML table matching the reference photo format.

    Each date renders as:
      Row 1 (테마): date cell (rowspan=2) | '테마' label | theme names across columns
      Row 2 (종목): '종목' label | stock lists across columns
    """
    if not history:
        return ""

    color_map = _build_sector_color_map(history)

    max_themes = max((len(d["themes"]) for d in history), default=1)
    col_headers = "".join(f"<th>{i + 1}</th>" for i in range(max_themes))
    head = f"<tr><th>날짜</th><th>구분</th>{col_headers}</tr>"

    rows_html = []
    for day in history:
        themes = day["themes"]
        pad = max_themes - len(themes)
        date_label = f"{day['date'][2:]}<br>({day['weekday']})"

        theme_cells = (
            "".join(
                f'<td class="history-theme-name" style="background:{color_map.get(t["theme"], "")}">'
                f'{escape(t["theme"])}</td>'
                for t in themes
            )
            + "<td></td>" * pad
        )

        stock_cells_parts = []
        for t in themes:
            bg = color_map.get(t["theme"], "")
            items = []
            for leader in t.get("leaders", []):
                change = float(leader["change"])
                color = _change_color(change)
                items.append(
                    f'<li style="color:{color}">'
                    f'{escape(leader["name"])} ({change:+.2f}%)'
                    f'</li>'
                )
            stock_cells_parts.append(
                f'<td style="background:{bg}">'
                f'<ul class="history-stock-list">{"".join(items)}</ul>'
                f'</td>'
            )
        stock_cells = "".join(stock_cells_parts) + "<td></td>" * pad

        rows_html.append(
            f'<tr>'
            f'<td class="history-date" rowspan="2">{date_label}</td>'
            f'<td class="history-label">테마</td>'
            f'{theme_cells}'
            f'</tr>'
            f'<tr>'
            f'<td class="history-label">종목</td>'
            f'{stock_cells}'
            f'</tr>'
        )

    return (
        '<div style="overflow-x:auto">'
        '<table class="history-board">'
        f'<thead>{head}</thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        '</table>'
        '</div>'
    )


def render_theme_history_table(history: list[dict]) -> None:
    """Render the date-by-date sector history board.

    Expects the output of get_theme_history() — list of dicts with
    'date', 'weekday', 'theme_count', 'themes'.
    """
    if not history:
        st.info("날짜별 섹터 히스토리 데이터가 없습니다.")
        return
    _html(_render_history_board_html(history))


def render_theme_timeline(timeline: pd.DataFrame) -> None:
    if timeline.empty:
        st.info("최근 테마 흐름 데이터가 아직 없습니다.")
        return

    required = [
        "date", "rank_1_theme", "rank_2_theme", "rank_3_theme",
        "top_leader_stock", "top_leader_change_rate",
        "total_trading_value", "market_comment", "badges",
    ]
    missing = _require_columns(timeline, required)
    if missing:
        st.warning(f"타임라인 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        st.dataframe(timeline, use_container_width=True, hide_index=True)
        return

    display = timeline[required].copy()
    display["top_leader_change_rate"] = display["top_leader_change_rate"].map(format_pct)
    display["total_trading_value"] = display["total_trading_value"].map(
        lambda v: format_krw(float(v or 0))
    )
    display = display.rename(columns={
        "date": "날짜",
        "rank_1_theme": "1위 테마",
        "rank_2_theme": "2위 테마",
        "rank_3_theme": "3위 테마",
        "top_leader_stock": "대장주",
        "top_leader_change_rate": "대장주 등락",
        "total_trading_value": "총 거래대금",
        "market_comment": "시장 코멘트",
        "badges": "배지",
    })
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "날짜":       st.column_config.TextColumn(width="small"),
            "1위 테마":   st.column_config.TextColumn(width="medium"),
            "2위 테마":   st.column_config.TextColumn(width="medium"),
            "3위 테마":   st.column_config.TextColumn(width="medium"),
            "대장주":     st.column_config.TextColumn(width="small"),
            "대장주 등락": st.column_config.TextColumn(width="small"),
            "총 거래대금": st.column_config.TextColumn(width="medium"),
            "시장 코멘트": st.column_config.TextColumn(width="large"),
            "배지":       st.column_config.TextColumn(width="small"),
        },
    )
