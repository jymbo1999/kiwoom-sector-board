from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import pandas as pd

from .sector_ranker import rank_intraday_leaders


def build_intraday_snapshot_payload(
    quotes: pd.DataFrame,
    universe: pd.DataFrame,
    previous_snapshot: dict[str, Any] | None = None,
    *,
    data_mode: str = "mock",
    provider_mode: str | None = None,
    generated_at: datetime | None = None,
    universe_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a repository-compatible intraday snapshot payload.

    The top-level `summary`, `themes`, and `leaders` keys match the existing
    sector snapshot shape. Extra keys are optional V1 metadata and can be ignored
    by the current DB layer without requiring a migration.
    """
    timestamp = generated_at or datetime.now()
    mode = provider_mode or data_mode
    ranked = rank_intraday_leaders(
        quotes,
        universe,
        previous_snapshot=previous_snapshot,
        generated_at=timestamp,
    )
    themes = _theme_view(ranked["themes"], ranked["leaders"], universe)
    leaders = _leader_view(ranked["leaders"])
    provider_status = dict(ranked.get("provider_status") or {})
    provider_status.setdefault("mode", "intraday_snapshot")
    provider_status["provider_mode"] = mode

    summary = dict(ranked.get("summary") or {})
    summary.update(
        {
            "board_type": "intraday",
            "data_mode": data_mode,
            "provider_mode": mode,
            "generated_at": timestamp.isoformat(timespec="seconds"),
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "freshness_seconds": _freshness_seconds(quotes, timestamp),
            "universe_count": _safe_unique_count(universe, "code"),
            "selected_sector_count": len(themes),
            "selected_leader_count": len(leaders),
        }
    )

    return {
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "summary": summary,
        "themes": themes,
        "leaders": leaders,
        "rank_events": ranked.get("rank_events") or [],
        "universe": universe_metadata or {"count": _safe_unique_count(universe, "code")},
        "provider_status": provider_status,
    }


def _theme_view(
    themes: list[dict[str, Any]],
    leaders: list[dict[str, Any]],
    universe: pd.DataFrame,
) -> list[dict[str, Any]]:
    leaders_by_theme: dict[str, list[dict[str, Any]]] = {}
    for leader in leaders:
        theme_id = str(leader.get("theme_id") or leader.get("theme_name") or "")
        leaders_by_theme.setdefault(theme_id, []).append(leader)

    market_cap_by_theme = _market_cap_by_theme(universe)
    rows: list[dict[str, Any]] = []
    for row in themes[:5]:
        theme_id = str(row.get("theme_id") or row.get("theme_name") or "")
        theme_leaders = sorted(
            leaders_by_theme.get(theme_id, []),
            key=lambda item: int(float(item.get("rank", 999) or 999)),
        )[:5]
        leader_labels = ", ".join(
            f"{leader.get('name', '')} ({float(leader.get('change_rate', 0.0) or 0.0):+.2f}%)"
            for leader in theme_leaders
        )
        leader_names = ", ".join(str(leader.get("name") or "") for leader in theme_leaders if leader.get("name"))
        total_trading_value = float(row.get("total_trading_value", 0.0) or 0.0)
        rows.append(
            {
                **row,
                "theme_id": theme_id,
                "theme_name": str(row.get("theme_name") or theme_id),
                "sector_score": float(row.get("theme_score", 0.0) or 0.0),
                "theme_score": float(row.get("theme_score", 0.0) or 0.0),
                "trade_value_sum": total_trading_value,
                "total_trading_value": total_trading_value,
                "market_cap": float(market_cap_by_theme.get(theme_id, 0.0)),
                "top5_change_rate_mean": float(row.get("top_leader_change_rate_mean", 0.0) or 0.0),
                "leader_names": leader_names,
                "leader_labels": leader_labels,
                "badges": _theme_badges(row),
            }
        )
    return _json_records(rows)


def _leader_view(leaders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in leaders:
        rows.append(
            {
                **row,
                "rank": int(float(row.get("rank", 0) or 0)),
                "theme_id": str(row.get("theme_id") or row.get("theme_name") or ""),
                "theme_name": str(row.get("theme_name") or row.get("theme_id") or ""),
                "code": str(row.get("code") or "").zfill(6),
                "name": str(row.get("name") or ""),
                "change_rate": float(row.get("change_rate", 0.0) or 0.0),
                "current_price": float(row.get("current_price", 0.0) or 0.0),
                "trade_value": float(row.get("trade_value", 0.0) or 0.0),
                "volume": float(row.get("volume", 0.0) or 0.0),
                "leader_score": float(row.get("leader_score", 0.0) or 0.0),
            }
        )
    return _json_records(rows)


def _theme_badges(row: dict[str, Any]) -> str:
    badges = []
    if float(row.get("top_leader_change_rate_mean", 0.0) or 0.0) >= 7.0:
        badges.append("급등")
    if float(row.get("total_trading_value", 0.0) or 0.0) > 0:
        badges.append("거래대금")
    if float(row.get("excess_return", 0.0) or 0.0) > 0:
        badges.append("시장대비 강세")
    return ",".join(badges)


def _market_cap_by_theme(universe: pd.DataFrame) -> dict[str, float]:
    if universe.empty or "theme" not in universe or "market_cap" not in universe:
        return {}
    frame = universe.copy()
    frame["theme"] = frame["theme"].fillna(frame.get("sector", "")).astype(str)
    frame["market_cap"] = pd.to_numeric(frame["market_cap"], errors="coerce").fillna(0.0)
    return frame.groupby("theme")["market_cap"].sum().to_dict()


def _freshness_seconds(quotes: pd.DataFrame, generated_at: datetime) -> int:
    if quotes.empty or "updated_at" not in quotes:
        return 0
    parsed = pd.to_datetime(quotes["updated_at"], errors="coerce").dropna()
    if parsed.empty:
        return 0
    latest = parsed.max().to_pydatetime()
    try:
        return max(0, int((generated_at - latest).total_seconds()))
    except TypeError:
        return 0


def _safe_unique_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].dropna().astype(str).nunique())


def _json_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(rows, ensure_ascii=False, default=_json_default))


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


# ---------------------------------------------------------------------------
# IntradaySnapshotService — v2 WebSocket 기반 순수 메모리 집계 서비스
# ---------------------------------------------------------------------------
# 기존 build_intraday_snapshot_payload(pandas 기반)와 무관하게 공존한다.
# DB 저장, Flask UI, 실제 WebSocket 연결과 무관한 순수 Python 서비스 레이어.
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass, field as _field

from .intraday_tick_aggregator import IntradayTickAggregator as _IntradayTickAggregator
from .intraday_sector_aggregator import aggregate_sector_minutes as _aggregate_sector_minutes
from .intraday_leader_ranker import (
    IntradaySectorLeaderView as _IntradaySectorLeaderView,
    rank_intraday_leaders as _rank_intraday_leaders_v2,
)
from .intraday_slot_manager import SlotManager as _SlotManager
from .kiwoom_websocket import normalize_tick_rows as _normalize_tick_rows


@_dataclass
class IntradaySnapshot:
    """장중 집계 스냅샷.

    status 의미:
      "empty"     - bucket이 하나도 없음 (아직 tick 미수신 또는 trade_time 이상)
      "warming"   - 런타임 실행 중이지만 아직 tick 미수신 (blueprint에서 설정)
      "no_leader" - bucket은 있지만 조건 만족 섹터가 없음 (+5%↑ 3개 미만)
      "ready"     - sector_views가 1개 이상 존재
    """

    generated_at: datetime
    minute_key: str | None
    sector_views: list[_IntradaySectorLeaderView]
    latest_count: int
    bucket_count: int
    raw_row_count: int
    ignored_row_count: int
    sector_count: int
    status: str  # "empty" | "warming" | "ready"
    unmapped_count: int = 0
    """tick 을 수신했지만 sector_map 에 없는 종목 수.
    warming 상태의 주요 원인 진단에 사용한다."""
    slot_layout: list = _field(default_factory=list)
    """슬롯 고정 배치 정보. 슬롯 1~9 의 섹터 카드 배치를 담는다."""
    extended_views: list = _field(default_factory=list)
    """min_riser_count=0 으로 산출한 전체 섹터 뷰. 조건 미달 섹터 포함."""


class IntradaySnapshotService:
    """장중 실시간 집계 서비스.

    normalize_tick_rows → IntradayTickAggregator → aggregate_sector_minutes
    → rank_intraday_leaders 파이프라인을 하나의 서비스로 묶는다.

    아직 collector 또는 Flask blueprint에 연결하지 않았다.
    """

    def __init__(
        self,
        sector_map: dict[str, list[str]],
        sector_limit: int = 5,
        stock_limit: int = 5,
        min_total_trade_value: int = 0,
        min_active_stock_count: int = 1,
        name_map: "dict[str, str] | None" = None,
        market_cap_map: "dict[str, int] | None" = None,
        min_riser_count: int = 3,
        # v3 호환 파라미터 (무시됨)
        min_strong_riser_count: int = 0,
    ) -> None:
        self.sector_map = sector_map
        self.sector_limit = sector_limit
        self.stock_limit = stock_limit
        self.min_total_trade_value = min_total_trade_value
        self.min_active_stock_count = min_active_stock_count
        self.name_map: dict[str, str] = name_map or {}
        self.market_cap_map: dict[str, int] = market_cap_map or {}
        self.min_riser_count = min_riser_count
        self.tick_aggregator = _IntradayTickAggregator()
        self.raw_row_count: int = 0
        self.ignored_row_count: int = 0
        self._slot_manager = _SlotManager()
        self._cached_slot_layout: list = []

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_raw_message(self, raw_message: "str | dict[str, Any]") -> int:
        """raw WebSocket 메시지를 파싱해 집계에 반영한다.

        normalize_tick_rows()로 파싱 후 tick_aggregator에 전달한다.
        파싱 실패 또는 REAL row가 없으면 ignored_row_count를 증가시키고 0을 반환한다.
        예외가 발생해도 서비스 전체가 중단되지 않는다.
        """
        try:
            rows = _normalize_tick_rows(raw_message)
        except Exception:
            self.ignored_row_count += 1
            return 0

        if not rows:
            self.ignored_row_count += 1
            return 0

        self.raw_row_count += len(rows)
        self.tick_aggregator.ingest_rows(rows)
        return len(rows)

    def ingest_rows(self, rows: "list[dict[str, Any]]") -> int:
        """이미 normalize된 row 리스트를 직접 집계에 반영한다 (테스트/내부 용도).

        base_code 또는 exchange가 없는 row는 무시하고 ignored_row_count에 집계한다.
        rows가 비어 있으면 ignored_row_count를 1 증가시키고 0을 반환한다.
        """
        if not rows:
            self.ignored_row_count += 1
            return 0

        self.raw_row_count += len(rows)
        valid = [r for r in rows if r.get("base_code") and r.get("exchange")]
        self.ignored_row_count += len(rows) - len(valid)

        if valid:
            self.tick_aggregator.ingest_rows(valid)
        return len(valid)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self, minute_key: "str | None" = None) -> IntradaySnapshot:
        """현재 집계 상태를 기반으로 IntradaySnapshot을 생성한다.

        minute_key가 주어지면 해당 분 기준으로 집계한다.
        None이면 aggregate_sector_minutes의 최신 분 자동 선택 정책을 따른다.
        """
        latest = self.tick_aggregator.get_latest_snapshot()
        buckets = self.tick_aggregator.get_minute_buckets()

        summaries = _aggregate_sector_minutes(
            buckets,
            self.sector_map,
            minute_key=minute_key,
            market_cap_map=self.market_cap_map or None,
        )
        market_cap_enabled = bool(self.market_cap_map)
        leadership_rule = (
            "v4_market_cap>=500B_riser5pct>=3_grade_ABC"
            if market_cap_enabled
            else "v4_riser5pct>=3_grade_ABC_no_mcap_filter"
        )
        sector_views = _rank_intraday_leaders_v2(
            summaries,
            sector_limit=self.sector_limit,
            stock_limit=self.stock_limit,
            min_total_trade_value=self.min_total_trade_value,
            min_active_stock_count=self.min_active_stock_count,
            min_riser_count=self.min_riser_count,
            market_cap_filter_min=500_000_000_000 if market_cap_enabled else 0,
            leadership_rule=leadership_rule,
        )
        if self.name_map:
            for sv in sector_views:
                for ls in sv.leader_stocks:
                    ls.stock_name = self.name_map.get(ls.base_code, "")

        actual_minute_key: "str | None" = None
        if buckets:
            actual_minute_key = minute_key if minute_key is not None else max(
                b.minute_key for b in buckets
            )

        if not buckets:
            status = "empty"
        elif not sector_views:
            status = "no_leader"
        else:
            status = "ready"

        unmapped_count = sum(
            1 for state in latest if state.base_code not in self.sector_map
        )

        # 자격 미달 섹터도 포함한 전체 뷰 (grace 기간 중 live 데이터 공급용)
        extended_views = _rank_intraday_leaders_v2(
            summaries,
            sector_limit=self.sector_limit,
            stock_limit=self.stock_limit,
            min_total_trade_value=self.min_total_trade_value,
            min_active_stock_count=self.min_active_stock_count,
            min_riser_count=0,
            market_cap_filter_min=500_000_000_000 if market_cap_enabled else 0,
            leadership_rule=leadership_rule,
        )
        if self.name_map:
            for sv in extended_views:
                for ls in sv.leader_stocks:
                    ls.stock_name = self.name_map.get(ls.base_code, "")

        if status == "ready":
            self._slot_manager.update(sector_views)
            self._cached_slot_layout = self._slot_manager.get_slot_layout(sector_views, extended_views)
        elif self._cached_slot_layout:
            # no_leader 상태에서도 grace 슬롯에 live 데이터 공급
            self._cached_slot_layout = self._slot_manager.get_slot_layout(sector_views, extended_views)
        slot_layout = self._cached_slot_layout

        return IntradaySnapshot(
            generated_at=datetime.now(),
            minute_key=actual_minute_key,
            sector_views=sector_views,
            latest_count=len(latest),
            bucket_count=len(buckets),
            raw_row_count=self.raw_row_count,
            ignored_row_count=self.ignored_row_count,
            sector_count=len(sector_views),
            status=status,
            unmapped_count=unmapped_count,
            slot_layout=slot_layout,
            extended_views=extended_views,
        )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """내부 집계기와 카운터를 초기화한다."""
        self.tick_aggregator = _IntradayTickAggregator()
        self.raw_row_count = 0
        self.ignored_row_count = 0
        self._slot_manager.reset()
        self._cached_slot_layout = []
