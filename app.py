from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import streamlit as st

from src.config import load_settings
from src.dashboard_components import (
    render_header,
    render_market_summary,
    render_morning_sector_card_board,
    render_pre_market_board,
    render_refresh_targets,
    render_rise_reason_summaries,
    render_theme_treemap,
)
from src.evidence_service import build_evidence_bundles
from src.market_data import (
    get_morning_board_view_models,
    get_refresh_schedule,
)
from src.rise_reason_service import summarize_rise_reasons
from src.snapshot_service import (
    compute_rank_changes,
    load_morning_view_models_from_snapshot,
    load_yesterday_heatmap,
    persist_morning_snapshot,
)


st.set_page_config(page_title="오늘의 주도섹터", layout="wide")


def load_board_view_models() -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Smart loader: snapshot warm-cache → API fetch with progress UI.

    Skips API entirely when a fresh local snapshot exists (< 90 s old),
    making cold starts from a new tab or app restart near-instant.
    At checkpoint crossings, session_state.force_fresh_fetch bypasses the cache.
    """
    force_fresh = st.session_state.get("force_fresh_fetch", False)
    if force_fresh:
        st.session_state.force_fresh_fetch = False
    else:
        cached = load_morning_view_models_from_snapshot(max_age_seconds=90)
        if cached is not None:
            return cached

    settings = load_settings()
    use_mock = settings.use_mock
    n_codes = settings.morning_board_max_codes or 40
    est_secs = int(n_codes * settings.api_request_interval_seconds)

    if use_mock:
        label = "샘플 데이터 로드 중..."
    else:
        label = f"시세 조회 중... ({n_codes}종목, 약 {est_secs}초 예상)"

    with st.status(label, expanded=not use_mock) as _status:
        progress_bar = None if use_mock else st.progress(0, text="종목 시세 조회 준비 중...")

        def _on_progress(done: int, total: int) -> None:
            if progress_bar is None:
                return
            remaining = int((total - done) * settings.api_request_interval_seconds)
            progress_bar.progress(
                done / total,
                text=f"종목 시세 조회 중... ({done}/{total})  |  약 {remaining}초 남음",
            )

        result = get_morning_board_view_models(on_progress=None if use_mock else _on_progress)

        if progress_bar is not None:
            progress_bar.progress(1.0, text="조회 완료")
        _status.update(label="데이터 로드 완료", state="complete", expanded=False)

    return result


@st.cache_data(ttl=3600)
def load_yesterday_data() -> pd.DataFrame:
    return load_yesterday_heatmap()


@st.cache_data(ttl=300)
def load_rise_reason_summaries(limit: int = 10) -> list[dict]:
    bundles = build_evidence_bundles(limit=limit)
    summaries = summarize_rise_reasons(bundles)
    by_ticker = {str(bundle.get("ticker", "")): bundle for bundle in bundles if isinstance(bundle, dict)}
    rows: list[dict] = []
    for summary in summaries:
        ticker = str(summary.get("ticker", ""))
        bundle = by_ticker.get(ticker, {})
        market_move = bundle.get("market_move", {}) if isinstance(bundle, dict) else {}
        row = dict(summary)
        row["market_move"] = market_move if isinstance(market_move, dict) else {}
        evidence_raw = bundle.get("evidence", []) if isinstance(bundle, dict) else []
        row["evidence_items_ui"] = [
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "excerpt": str(item.get("excerpt", "")),
                "provider": str(item.get("provider", "")),
                "published_at": str(item.get("published_at", "")),
                "source_type": str(item.get("source_type", "")),
            }
            for item in (evidence_raw if isinstance(evidence_raw, list) else [])[:5]
        ]
        rows.append(row)
    return rows


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


def _auto_refresh_if_checkpoint_crossed(refresh_schedule: dict) -> None:
    """Force a fresh API fetch once per checkpoint crossing."""
    last_cp = refresh_schedule.get("last_checkpoint")
    if last_cp is None:
        return
    key = last_cp.isoformat()
    if "refreshed_checkpoints" not in st.session_state:
        st.session_state.refreshed_checkpoints = set()
    if key not in st.session_state.refreshed_checkpoints:
        st.session_state.refreshed_checkpoints.add(key)
        st.session_state.force_fresh_fetch = True  # bypass snapshot cache on next run
        st.cache_data.clear()
        st.rerun()


def main() -> None:
    now = datetime.now()
    refresh_schedule = get_refresh_schedule(now)

    # Trigger immediate cache-clear on checkpoint crossing (once per checkpoint)
    _auto_refresh_if_checkpoint_crossed(refresh_schedule)

    load_error = None
    try:
        summary, heatmap, leaders = load_board_view_models()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        summary, heatmap, leaders, load_error = _empty_board_state(exc)

    render_header(now, bool(summary.get("effective_mock")), refresh_schedule)
    render_refresh_targets()

    error_message = load_error or summary.get("error_message")
    if error_message:
        st.warning(error_message)
    if summary.get("effective_mock"):
        st.info("샘플 데이터로 화면을 표시 중입니다. 투자 추천이 아닌 UI 확인용 데이터입니다.")

    yesterday_heatmap = load_yesterday_data()
    rank_changes = compute_rank_changes(heatmap, yesterday_heatmap, sector_limit=12)

    render_market_summary(summary)

    # 장전(08:00~09:00): 어제 스냅샷 기반 준비판 먼저 표시
    if refresh_schedule.get("market_phase") == "pre_market":
        render_pre_market_board(yesterday_heatmap)
        st.divider()

    render_morning_sector_card_board(heatmap, leaders, sector_limit=12, rank_changes=rank_changes)
    try:
        snapshot_result = persist_morning_snapshot(summary, heatmap, leaders)
    except OSError as exc:
        st.caption(f"스냅샷 저장 실패: {exc}")
    else:
        if snapshot_result.get("r2_status") == "uploaded":
            st.caption(f"스냅샷 저장 완료: R2 {snapshot_result.get('r2_key')}")
        else:
            st.caption(f"스냅샷 저장 완료: {snapshot_result.get('local_path')}")
        if snapshot_result.get("sector_db_status"):
            st.caption(f"섹터보드 DB 저장 상태: {snapshot_result.get('sector_db_status')}")

    with st.expander("상승이유/뉴스 보조 정보", expanded=False):
        try:
            rise_reason_summaries = load_rise_reason_summaries(limit=10)
        except Exception as exc:
            st.warning(f"상승이유 요약 데이터를 불러오지 못했습니다: {exc}")
            rise_reason_summaries = []
        render_rise_reason_summaries(rise_reason_summaries)
        st.caption("상승이유 요약은 수집된 네이버 뉴스 snippet을 문단으로 정리한 보조 정보이며, 투자 추천이나 매수·매도 권유가 아닙니다.")

    theme_options = heatmap["theme_id"].astype(str).tolist() if "theme_id" in heatmap and not heatmap.empty else []

    st.subheader("테마 흐름")
    _SIZE_OPTIONS = {
        "total_trading_value": "테마 거래대금",
        "market_cap": "시가총액",
        "theme_score": "테마 점수",
        "equal": "동일 크기",
    }
    size_by = st.selectbox(
        "박스 크기 기준",
        options=list(_SIZE_OPTIONS.keys()),
        format_func=lambda k: _SIZE_OPTIONS[k],
        key="treemap_size_by",
    )
    render_theme_treemap(heatmap, size_by=size_by)
    if not theme_options:
        st.info("선택 가능한 테마 데이터가 없습니다.")

    # Periodic rerun during market hours to catch checkpoint crossings.
    # Sleep at most 30s so the countdown in the header stays reasonably accurate.
    market_phase = refresh_schedule.get("market_phase", "closed")
    if market_phase in ("pre_market", "regular_market"):
        secs_until = refresh_schedule.get("seconds_until")
        sleep_secs = min(30, secs_until) if secs_until is not None else 30
        if sleep_secs > 0:
            time.sleep(sleep_secs)
        st.rerun()


if __name__ == "__main__":
    main()
