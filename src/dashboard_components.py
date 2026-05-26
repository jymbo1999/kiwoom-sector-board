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
        .featured-theme-card {
            border-color: var(--sector-border, rgba(255,255,255,0.24));
            background:
                linear-gradient(135deg, var(--sector-bg, rgba(255,255,255,0.07)), rgba(255,255,255,0.035));
        }
        .featured-theme-card .sector-card-header {
            background: var(--sector-header, rgba(255,255,255,0.12));
            color: #ffffff;
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
        .leader-rate-chip {
            border-radius: 4px;
            padding: 2px 7px;
            color: #241200;
            font-weight: 700;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.2);
        }
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
        .rise-reason-name-line {
            display: flex;
            align-items: center;
            gap: 7px;
            flex-wrap: wrap;
        }
        .rise-reason-code {
            color: rgba(255,255,255,0.48);
            font-size: 0.82rem;
            white-space: nowrap;
            margin-top: 2px;
        }
        .rise-reason-summary {
            line-height: 1.48;
            overflow-wrap: anywhere;
        }
        .rise-reason-table th:nth-child(1) { width: 12%; }
        .rise-reason-table th:nth-child(2) { width: 18%; }
        .rise-reason-table th:nth-child(3) { width: 36%; }
        .rise-reason-table th:nth-child(4) { width: 23%; }
        .rise-reason-table th:nth-child(5) { width: 11%; }
        .rise-reason-stock {
            min-width: 150px;
        }
        .rate-heat-badge {
            display: inline-block;
            min-width: 66px;
            border-radius: 4px;
            padding: 2px 7px;
            text-align: center;
            font-size: 0.78rem;
            font-weight: 700;
            color: #241200;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.22);
        }
        .evidence-confidence {
            margin-bottom: 6px;
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
        /* ── Evidence detail popup (details/summary) ── */
        .evidence-detail {
            list-style: none;
            padding: 0;
            margin: 0;
            min-width: 220px;
            max-width: 340px;
        }
        .evidence-detail li {
            margin: 0 0 2px;
        }
        .evidence-detail details > summary {
            color: rgba(255,255,255,0.78);
            font-size: 0.83rem;
            line-height: 1.38;
            padding: 3px 0 3px 14px;
            cursor: pointer;
            list-style: none;
            position: relative;
            overflow-wrap: anywhere;
        }
        .evidence-detail details > summary::-webkit-details-marker { display: none; }
        .evidence-detail details > summary::before {
            content: "▸";
            position: absolute;
            left: 0;
            color: rgba(255,255,255,0.35);
            font-size: 0.72em;
            top: 5px;
        }
        .evidence-detail details[open] > summary::before { content: "▾"; }
        .evidence-popup {
            background: rgba(255,255,255,0.07);
            border: solid 1px rgba(255,255,255,0.14);
            border-radius: 4px;
            padding: 8px 10px;
            margin: 4px 0 6px 14px;
            font-size: 0.8rem;
            line-height: 1.45;
            color: rgba(255,255,255,0.6);
        }
        .evidence-popup .ev-meta {
            color: rgba(255,255,255,0.38);
            font-size: 0.74rem;
            margin-bottom: 5px;
            letter-spacing: 0.02rem;
        }
        .evidence-popup .ev-excerpt {
            margin: 0 0 6px;
            overflow-wrap: anywhere;
        }
        .evidence-popup a {
            color: #5dade2;
            font-size: 0.77rem;
            text-decoration: none;
            word-break: break-all;
        }
        .evidence-popup a:hover { text-decoration: underline; }
        </style>
        """
    )


def _format_next_refresh(refresh_schedule: dict | None) -> str:
    if not refresh_schedule:
        return "09:03 / 09:15 / 10:00"
    next_cp = refresh_schedule.get("next_checkpoint")
    secs = refresh_schedule.get("seconds_until")
    if next_cp is None or secs is None:
        phase = refresh_schedule.get("market_phase", "closed")
        return "장마감" if phase == "after_market" else "장외"
    mins, remainder = divmod(int(secs), 60)
    label = next_cp.strftime("%H:%M")
    if mins > 0:
        return f"다음 갱신 {label} ({mins}분 {remainder:02d}초 후)"
    return f"다음 갱신 {label} ({remainder}초 후)"


def render_header(
    reference_time: datetime,
    use_mock: bool | None = None,
    refresh_schedule: dict | None = None,
) -> None:
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
    if button_col.button("새로고침", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    data_mode = "확인 중" if use_mock is None else ("Mock" if use_mock else "Kiwoom REST")
    next_refresh_label = _format_next_refresh(refresh_schedule)
    _html(
        f"""
        <div class="board-meta">
            <div class="board-meta-item">기준 시각<strong>{escape(reference_time.strftime("%Y-%m-%d %H:%M:%S"))}</strong></div>
            <div class="board-meta-item">데이터 모드<strong>{data_mode}</strong></div>
            <div class="board-meta-item">{escape(next_refresh_label)}</div>
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


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{max(0.0, min(1.0, alpha)):.2f})"


def _mix_hex(start_hex: str, end_hex: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    start = _hex_to_rgb(start_hex)
    end = _hex_to_rgb(end_hex)
    mixed = [round(start[i] + (end[i] - start[i]) * ratio) for i in range(3)]
    return f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"


def _range_ratio(value: float, min_value: float, max_value: float) -> float:
    if max_value <= min_value:
        return 1.0 if value > 0 else 0.5
    return (value - min_value) / (max_value - min_value)


def _rise_heat_color(value: float, min_value: float, max_value: float) -> str:
    """Map lowest value to yellow and highest value to red for Korean rise heat."""
    ratio = _range_ratio(value, min_value, max_value)
    return _mix_hex("#ffe66d", "#e8212e", ratio)


def _rate_heat_badge_html(value: float, min_value: float, max_value: float, *, css_class: str = "rate-heat-badge") -> str:
    color = _rise_heat_color(value, min_value, max_value)
    return (
        f'<span class="{css_class}" style="background:{color}">'
        f'{value:+.2f}%</span>'
    )


def _confidence_badge_html(confidence: str) -> str:
    value = str(confidence or "unknown").lower()
    if value not in {"high", "medium", "low", "unknown"}:
        value = "unknown"
    return f'<span class="confidence-badge confidence-{value}">{escape(value)}</span>'


def _rise_reason_rows(summaries: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        market_move = summary.get("market_move", {})
        if not isinstance(market_move, dict):
            market_move = {}
        evidence_items_ui = summary.get("evidence_items_ui", [])
        if not isinstance(evidence_items_ui, list):
            evidence_items_ui = []
        # Fallback: use plain titles when no URL-bearing items are available
        evidence_titles = summary.get("evidence_titles", [])
        if not isinstance(evidence_titles, list):
            evidence_titles = []
        rows.append(
            {
                "name": str(summary.get("name", "")),
                "ticker": str(summary.get("ticker", "")),
                "pct_change_value": _coerce_float(market_move.get("pct_change", 0.0)),
                "pct_change": format_pct(market_move.get("pct_change", 0.0)),
                "sector": str(market_move.get("sector", "")),
                "reason_summary_ko": str(summary.get("reason_summary_ko", "")),
                "confidence": str(summary.get("confidence", "unknown")),
                "evidence_items_ui": evidence_items_ui[:5],
                "evidence_titles_fallback": [str(t) for t in evidence_titles[:5] if str(t).strip()],
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

    change_values = [_coerce_float(row.get("pct_change_value")) for row in rows]
    change_min = min(change_values, default=0.0)
    change_max = max(change_values, default=0.0)

    row_html = []
    for row in rows:
        items_ui: list[dict] = row["evidence_items_ui"]
        fallback_titles: list[str] = row["evidence_titles_fallback"]
        change = _coerce_float(row.get("pct_change_value"))
        change_badge = _rate_heat_badge_html(change, change_min, change_max)

        if items_ui:
            li_parts = []
            for item in items_ui:
                title = escape(str(item.get("title", "")).strip()) or "(제목 없음)"
                url = str(item.get("url", "")).strip()
                excerpt = escape(str(item.get("excerpt", "")).strip())
                provider = escape(str(item.get("provider", "")).strip())
                published_at = escape(str(item.get("published_at", "")).strip())
                meta = " · ".join(p for p in [provider, published_at] if p)
                popup_inner = ""
                if meta:
                    popup_inner += f'<div class="ev-meta">{meta}</div>'
                if excerpt:
                    popup_inner += f'<div class="ev-excerpt">{excerpt}</div>'
                if url:
                    popup_inner += f'<a href="{url}" target="_blank" rel="noopener">원문 보기 ↗</a>'
                popup = f'<div class="evidence-popup">{popup_inner}</div>' if popup_inner else ""
                li_parts.append(f"<li><details><summary>{title}</summary>{popup}</details></li>")
            evidence_html = '<ul class="evidence-detail">' + "".join(li_parts) + "</ul>"
        elif fallback_titles:
            li_parts = [f"<li><span style='color:rgba(255,255,255,0.65);font-size:0.83rem'>{escape(t)}</span></li>" for t in fallback_titles]
            evidence_html = '<ul class="evidence-detail">' + "".join(li_parts) + "</ul>"
        else:
            evidence_html = '<span style="color:rgba(255,255,255,0.3);font-size:0.82rem">-</span>'

        evidence_with_confidence = (
            f'<div class="evidence-confidence">{_confidence_badge_html(row["confidence"])}</div>'
            f"{evidence_html}"
        )

        row_html.append(
            "<tr>"
            f'<td>{escape(row["sector"])}</td>'
            f'<td><div class="rise-reason-stock">'
            f'<div class="rise-reason-name-line"><span class="rise-reason-name">{escape(row["name"])}</span>{change_badge}</div>'
            f'<div class="rise-reason-code">{escape(row["ticker"])}</div>'
            f'</div></td>'
            f'<td><div class="rise-reason-summary">{escape(row["reason_summary_ko"])}</div></td>'
            f"<td>{evidence_with_confidence}</td>"
            f'<td><div class="rise-reason-summary">{escape(row["caveat"])}</div></td>'
            "</tr>"
        )

    _html(
        """
        <div style="overflow-x:auto">
        <table class="summary-table rise-reason-table">
            <thead>
                <tr>
                    <th>섹터</th>
                    <th>종목명</th>
                    <th>상승이유 요약</th>
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


def _rank_change_label(change: str) -> str:
    """Return rank change label with emoji indicator."""
    if change == "NEW":
        return "🆕 NEW"
    if change == "=":
        return "="
    if change.startswith("▲"):
        return f"🔺{change[1:]}"
    if change.startswith("▼"):
        return f"🔻{change[1:]}"
    return change


def render_pre_market_board(yesterday_heatmap: pd.DataFrame) -> None:
    """Render a pre-market summary using yesterday's snapshot data."""
    st.subheader("📋 장전 준비판 — 어제 주도섹터 기준")
    if yesterday_heatmap.empty or "theme_name" not in yesterday_heatmap.columns:
        st.info("어제 스냅샷이 없습니다. 장 종료 후 자동 저장된 스냅샷이 쌓이면 여기에 표시됩니다.")
        return

    score_col = "theme_score" if "theme_score" in yesterday_heatmap.columns else None
    tv_col = "total_trading_value" if "total_trading_value" in yesterday_heatmap.columns else None
    sort_cols = [c for c in [score_col, tv_col] if c]
    ranked = yesterday_heatmap.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(10).copy()
    ranked["전일순위"] = range(1, len(ranked) + 1)

    display_cols = ["전일순위", "theme_name"]
    rename = {"theme_name": "섹터"}
    if score_col:
        display_cols.append(score_col)
        rename[score_col] = "섹터점수"
    if "top5_change_rate_mean" in ranked.columns:
        display_cols.append("top5_change_rate_mean")
        rename["top5_change_rate_mean"] = "TOP5 평균등락률"
    if tv_col:
        display_cols.append(tv_col)
        rename[tv_col] = "거래대금"
    if "leader_labels" in ranked.columns:
        display_cols.append("leader_labels")
        rename["leader_labels"] = "어제 대장주"

    table = ranked[display_cols].rename(columns=rename)
    if "섹터점수" in table:
        table["섹터점수"] = table["섹터점수"].map(lambda v: f"{float(v or 0):.2f}")
    if "TOP5 평균등락률" in table:
        table["TOP5 평균등락률"] = table["TOP5 평균등락률"].map(format_pct)
    if "거래대금" in table:
        table["거래대금"] = table["거래대금"].map(lambda v: format_krw(float(v or 0)))

    st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption("어제 장마감 기준 스냅샷입니다. 오늘 장 시작 후 09:03 데이터로 자동 교체됩니다.")


def _render_morning_card_html(
    row: pd.Series,
    sector_leaders: pd.DataFrame,
    rank: int,
    rank_change: str,
    change_min: float,
    change_max: float,
) -> str:
    sector_name = str(row.get("theme_name", ""))
    score = float(row.get("theme_score") or 0.0)
    rising_ratio = float(row.get("rising_ratio") or 0.0)
    trade_value = float(row.get("total_trading_value") or 0.0)

    badge_html = ""
    if rank_change and rank_change not in ("-", ""):
        label = _rank_change_label(rank_change)
        badge_html = (
            f' <span style="font-size:0.72rem;opacity:0.62;font-weight:300">'
            f"{escape(label)}</span>"
        )

    leader_items = []
    if not sector_leaders.empty:
        for leader in sector_leaders.sort_values("rank").head(5).itertuples(index=False):
            change = float(leader.change_rate or 0)
            change_badge = _rate_heat_badge_html(change, change_min, change_max, css_class="leader-rate-chip")
            leader_items.append(
                "<li>"
                f'<span class="leader-name">{int(leader.rank)}. {escape(str(leader.name))} '
                f'<small style="opacity:.5">({escape(str(leader.code))})</small></span>'
                f'<span class="leader-rate">{change_badge}</span>'
                "</li>"
            )

    leaders_html = f'<ul class="leader-list">{"".join(leader_items)}</ul>' if leader_items else ""

    return (
        '<article class="sector-card">'
        f'<div class="sector-card-header">{rank}. {escape(sector_name)}{badge_html}</div>'
        '<div class="sector-card-body">'
        '<div class="sector-stats">'
        f'<div class="sector-stat">점수<strong>{score:.2f}</strong></div>'
        f'<div class="sector-stat">상승비율<strong>{rising_ratio * 100:.0f}%</strong></div>'
        f'<div class="sector-stat">거래대금<strong>{format_krw(trade_value)}</strong></div>'
        "</div>"
        + leaders_html
        + "</div>"
        "</article>"
    )


def render_morning_sector_card_board(
    heatmap: pd.DataFrame,
    leaders: pd.DataFrame,
    sector_limit: int = 12,
    rank_changes: dict[str, str] | None = None,
) -> None:
    """Merged morning board: sector cards with embedded leader stocks."""
    if heatmap.empty:
        st.info("주도섹터를 계산할 데이터가 없습니다.")
        return

    ranked = heatmap.sort_values(
        ["theme_score", "total_trading_value"],
        ascending=[False, False],
    ).head(sector_limit).reset_index(drop=True)

    top_theme_ids = ranked["theme_id"].astype(str).tolist()
    top_leaders = (
        leaders[leaders["theme_id"].astype(str).isin(top_theme_ids)].copy()
        if not leaders.empty
        else pd.DataFrame()
    )
    changes = (
        pd.to_numeric(top_leaders["change_rate"], errors="coerce").dropna().tolist()
        if not top_leaders.empty
        else []
    )
    change_min = float(min(changes, default=0.0))
    change_max = float(max(changes, default=0.0))

    st.subheader("오늘의 주도섹터")
    cards = []
    for i, (_, row) in enumerate(ranked.iterrows(), start=1):
        theme_id = str(row["theme_id"])
        sector_leaders = (
            top_leaders[top_leaders["theme_id"].astype(str) == theme_id]
            if not top_leaders.empty
            else pd.DataFrame()
        )
        rank_change = rank_changes.get(str(row["theme_name"]), "-") if rank_changes else "-"
        cards.append(_render_morning_card_html(row, sector_leaders, i, rank_change, change_min, change_max))

    _html(f'<section class="sector-board">{"".join(cards)}</section>')


def _fallback_theme_table(heatmap: pd.DataFrame) -> None:
    display_columns = [
        "theme_name",
        "theme_score",
        "top5_change_rate_mean",
        "rising_ratio",
        "total_trading_value",
        "leader_labels",
    ]
    available = [column for column in display_columns if column in heatmap.columns]
    table = heatmap[available].copy()
    rename_map = {
        "theme_name": "테마",
        "theme_score": "점수",
        "top5_change_rate_mean": "Top5 평균 등락률",
        "rising_ratio": "상승비율",
        "total_trading_value": "거래대금",
        "leader_labels": "대표 대장주",
    }
    table = table.rename(columns=rename_map)
    if "거래대금" in table:
        table["거래대금"] = table["거래대금"].map(lambda value: format_krw(float(value or 0)))
    if "상승비율" in table:
        table["상승비율"] = table["상승비율"].map(lambda value: f"{float(value or 0) * 100:.0f}%")
    st.dataframe(table, width="stretch", hide_index=True)


_SIZE_BY_LABELS: dict[str, str] = {
    "total_trading_value": "테마 거래대금",
    "market_cap": "시가총액",
    "theme_score": "테마 점수",
    "equal": "동일 크기",
}


def render_theme_treemap(heatmap: pd.DataFrame, size_by: str = "total_trading_value") -> None:
    """Render a Plotly treemap when available, otherwise a safe table heatmap fallback."""

    required = ["theme_name", "total_trading_value", "top5_change_rate_mean", "leader_labels"]
    if heatmap.empty:
        st.info("테마 흐름을 표시할 데이터가 없습니다.")
        return

    missing = _require_columns(heatmap, required)
    if missing:
        st.warning(f"테마 데이터 컬럼이 부족합니다: {', '.join(missing)}")
        _fallback_theme_table(heatmap)
        return

    size_label = _SIZE_BY_LABELS.get(size_by, size_by)
    st.caption(f"박스 크기 = {size_label}  ·  색상 = 평균 등락률(상승 빨강 / 하락 파랑)")

    chart_data = heatmap.copy()
    chart_data["total_trading_value"] = pd.to_numeric(chart_data["total_trading_value"], errors="coerce").fillna(0.0)
    chart_data["top5_change_rate_mean"] = pd.to_numeric(chart_data["top5_change_rate_mean"], errors="coerce").fillna(0.0)
    chart_data["leader_preview"] = chart_data["leader_labels"].astype(str).map(
        lambda names: "<br>".join([name.strip() for name in names.split(",")[:3] if name.strip()])
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
        color_continuous_scale=[(0.0, "#2457c5"), (0.5, "#30343d"), (1.0, "#e93b43")],
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
        height=680,
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(
            tickfont=dict(color="rgba(255,255,255,0.6)"),
            title=dict(text="평균 %", font=dict(color="rgba(255,255,255,0.6)")),
        ),
    )
    st.plotly_chart(fig, width="stretch")


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
        st.dataframe(leaders, width="stretch", hide_index=True)
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
        width="stretch",
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


def _theme_change_bounds(themes: list[dict]) -> tuple[float, float]:
    changes = [
        _coerce_float(leader.get("change"))
        for theme in themes
        for leader in theme.get("leaders", [])
        if isinstance(leader, dict)
    ]
    return min(changes, default=0.0), max(changes, default=0.0)


def _render_featured_theme_card_html(
    theme_data: dict,
    color_map: dict[str, str],
    change_min: float,
    change_max: float,
) -> str:
    theme_name = str(theme_data.get("theme", ""))
    sector_color = color_map.get(theme_name, "#4f8cff")
    leader_items = []
    for i, leader in enumerate(theme_data.get("leaders", [])[:5], start=1):
        change = _coerce_float(leader.get("change", 0))
        change_badge = _rate_heat_badge_html(change, change_min, change_max, css_class="leader-rate-chip")
        leader_items.append(
            "<li>"
            f"<span class=\"leader-name\">{i}. {escape(str(leader['name']))}</span>"
            f"<span class=\"leader-rate\">{change_badge}</span>"
            "</li>"
        )
    return (
        '<article class="sector-card featured-theme-card" '
        f'style="--sector-bg:{_rgba(sector_color, 0.20)};'
        f'--sector-header:{_rgba(sector_color, 0.34)};'
        f'--sector-border:{_rgba(sector_color, 0.62)}">'
        f'<div class="sector-card-header">{escape(theme_name)}</div>'
        '<div class="sector-card-body">'
        f'<div class="sector-reason">{escape(str(theme_data.get("reason", "")))}</div>'
        f'<ul class="leader-list">{"".join(leader_items)}</ul>'
        "</div>"
        "</article>"
    )


def render_featured_themes(themes: list[dict], history: list[dict] | None = None) -> None:
    """Render today's featured sector theme cards using the existing sector-card grid CSS."""

    if not themes:
        st.info("오늘의 특징테마 데이터가 없습니다.")
        return
    color_map = _build_sector_color_map(history or [{"themes": themes}])
    change_min, change_max = _theme_change_bounds(themes)
    cards = [_render_featured_theme_card_html(t, color_map, change_min, change_max) for t in themes]
    _html(f'<section class="sector-board">{"".join(cards)}</section>')


# High-contrast palette — consistent across theme names in featured cards and history board.
_SECTOR_BG_PALETTE = [
    "#ff5f57",  # coral red
    "#21b8a6",  # teal
    "#f7b731",  # amber
    "#4f8cff",  # vivid blue
    "#b56cff",  # violet
    "#34c759",  # green
    "#ff7ab6",  # pink
    "#00a8ff",  # cyan-blue
    "#ff8f3d",  # orange
    "#8bd450",  # lime
    "#d95f02",  # burnt orange
    "#6c8cff",  # periwinkle
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
        for t in day.get("themes", []):
            theme_name = str(t.get("theme", ""))
            if theme_name and theme_name not in seen:
                seen.append(theme_name)
    return {
        name: _SECTOR_BG_PALETTE[i % len(_SECTOR_BG_PALETTE)]
        for i, name in enumerate(seen)
    }


def _build_sector_key_map(history: list[dict]) -> dict[str, str]:
    return {theme_name: f"sector-{idx}" for idx, theme_name in enumerate(_build_sector_color_map(history))}


def _history_focus_labels(sector_key: str, inner_html: str) -> str:
    return (
        f'<label class="focus-label focus-on" for="history-focus-{sector_key}">{inner_html}</label>'
        f'<label class="focus-label focus-off" for="history-focus-none">{inner_html}</label>'
    )


def _render_history_board_html(history: list[dict]) -> str:
    """Build the 2-row-per-date HTML table matching the reference photo format.

    Each date renders as:
      Row 1 (테마): date cell (rowspan=2) | '테마' label | theme names across columns
      Row 2 (종목): '종목' label | stock lists across columns
    """
    if not history:
        return ""

    color_map = _build_sector_color_map(history)
    key_map = _build_sector_key_map(history)

    max_themes = max((len(d["themes"]) for d in history), default=1)
    col_headers = "".join(f"<th>{i + 1}</th>" for i in range(max_themes))
    head = f"<tr><th>날짜</th><th>구분</th>{col_headers}</tr>"
    focus_inputs = (
        '<input class="focus-control" type="radio" name="history-sector-focus" '
        'id="history-focus-none" checked>'
        + "".join(
            f'<input class="focus-control" type="radio" name="history-sector-focus" '
            f'id="history-focus-{sector_key}">'
            for sector_key in key_map.values()
        )
    )
    focus_css = "".join(
        f"""
        #history-focus-{sector_key}:checked ~ table .history-sector-cell[data-sector-key="{sector_key}"] {{
            opacity: 1;
            filter: saturate(1.28);
            box-shadow: inset 0 0 0 2px var(--sector-border), 0 0 0 1px rgba(255,255,255,0.10);
        }}
        #history-focus-{sector_key}:checked ~ table .history-sector-cell[data-sector-key="{sector_key}"] .focus-on {{
            display: none;
        }}
        #history-focus-{sector_key}:checked ~ table .history-sector-cell[data-sector-key="{sector_key}"] .focus-off {{
            display: block;
        }}
        """
        for sector_key in key_map.values()
    )

    rows_html = []
    for day in history:
        themes = day["themes"]
        pad = max_themes - len(themes)
        date_label = f"{day['date'][2:]}<br>({day['weekday']})"

        theme_cells_parts = []
        for t in themes:
            theme_name = str(t["theme"])
            color = color_map.get(theme_name, "#4f8cff")
            sector_key = key_map.get(theme_name, "sector-unknown")
            theme_cells_parts.append(
                f'<td class="history-theme-name history-sector-cell" '
                f'data-sector-key="{escape(sector_key)}" '
                f'style="--sector-bg:{_rgba(color, 0.26)};--sector-border:{_rgba(color, 0.72)}">'
                f'{_history_focus_labels(sector_key, escape(theme_name))}</td>'
            )
        theme_cells = "".join(theme_cells_parts) + "<td></td>" * pad

        stock_cells_parts = []
        for t in themes:
            theme_name = str(t["theme"])
            sector_key = key_map.get(theme_name, "sector-unknown")
            sector_color = color_map.get(theme_name, "#4f8cff")
            items = []
            for leader in t.get("leaders", []):
                change = float(leader["change"])
                color = _change_color(change)
                items.append(
                    f'<li style="color:{color}">'
                    f'{escape(leader["name"])} ({change:+.2f}%)'
                    f'</li>'
                )
            stock_list_html = f'<ul class="history-stock-list">{"".join(items)}</ul>'
            stock_cells_parts.append(
                f'<td class="history-sector-cell" '
                f'data-sector-key="{escape(sector_key)}" '
                f'style="--sector-bg:{_rgba(sector_color, 0.18)};'
                f'--sector-border:{_rgba(sector_color, 0.62)}">'
                f'{_history_focus_labels(sector_key, stock_list_html)}'
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
        """
        <style>
        .history-wrap { overflow-x: auto; padding: 1px; }
        .history-wrap .focus-control {
            position: absolute;
            opacity: 0;
            pointer-events: none;
        }
        .history-wrap:has(.focus-control:not(#history-focus-none):checked) .history-sector-cell {
            opacity: 0.22;
            filter: grayscale(0.6) saturate(0.35);
        }
        .history-wrap .focus-label {
            display: block;
            width: 100%;
            min-height: 100%;
            cursor: pointer;
        }
        .history-wrap .focus-off {
            display: none;
        }
        .history-board {
            width: 100%;
            border-collapse: collapse;
            color: #ffffff;
            font-size: 0.92rem;
        }
        .history-board th {
            background: rgba(255,255,255,0.08);
            border: solid 1px rgba(255,255,255,0.2);
            padding: 8px 12px;
            text-align: center;
            font-weight: 600;
            font-size: 0.82rem;
            color: rgba(255,255,255,0.62);
            letter-spacing: 0.05rem;
        }
        .history-board td {
            border: solid 1px rgba(255,255,255,0.1);
            padding: 8px 12px;
            vertical-align: top;
            transition: opacity 140ms ease, filter 140ms ease, box-shadow 140ms ease, background 140ms ease;
        }
        .history-date {
            text-align: center;
            white-space: nowrap;
            font-weight: 600;
            color: rgba(255,255,255,0.82);
            font-size: 0.88rem;
            background: rgba(255,255,255,0.05);
        }
        .history-label {
            text-align: center;
            color: rgba(255,255,255,0.48);
            font-size: 0.82rem;
            font-weight: 400;
            white-space: nowrap;
            background: rgba(255,255,255,0.03);
        }
        .history-sector-cell {
            background: var(--sector-bg);
            box-shadow: inset 0 0 0 1px transparent;
            cursor: pointer;
        }
        .history-theme-name {
            font-weight: 700;
            color: rgba(255,255,255,0.96);
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
            font-weight: 400;
            white-space: nowrap;
        }
        """
        + focus_css
        + """
        </style>
        <div class="history-wrap" data-history-board>
        """
        f"{focus_inputs}"
        '<table class="history-board">'
        f'<thead>{head}</thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        '</table>'
        """
        </div>
        """
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
        st.dataframe(timeline, width="stretch", hide_index=True)
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
        width="stretch",
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
