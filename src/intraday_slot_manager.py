"""장중 섹터 카드 고정 슬롯 배치 관리자.

IntradaySnapshotService 가 보유하며 sector_views 변화에 따라
슬롯 1~9 의 섹터 배치를 관리한다.

배치 규칙:
  - 최초 ready 시: 상위 4개를 슬롯 1~4 에 배치, 5~9 는 비움
  - 이후 업데이트:
      · 탈락 섹터의 슬롯만 None 으로 비움 (다른 슬롯 앞당김 없음)
      · 신규 섹터는 빈 슬롯에 번호 순서대로 채움
      · 기존 섹터 간 점수 순위 변동에 의한 재정렬 없음
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .intraday_leader_ranker import IntradaySectorLeaderView

# ---------------------------------------------------------------------------
# 섹터별 고유 색상 팔레트
# ---------------------------------------------------------------------------

SECTOR_COLORS: dict[str, str] = {
    "로봇": "#7C3AED",
    "반도체": "#2563EB",
    "바이오": "#059669",
    "2차전지": "#EA580C",
    "전력기기": "#DC2626",
    "원전": "#0891B2",
    "조선": "#0F766E",
    "방산": "#4D7C0F",
    "증권": "#9333EA",
    "은행": "#0369A1",
    "보험": "#BE123C",
    "AI": "#DB2777",
    "자동차": "#B45309",
    "철강": "#64748B",
    "화학": "#0D9488",
    "게임": "#6D28D9",
    "엔터": "#EC4899",
    "건설": "#92400E",
    "유통": "#1D4ED8",
    "식품": "#15803D",
    "의료기기": "#0E7490",
    "통신": "#4338CA",
    "항공": "#7E22CE",
    "에너지": "#B91C1C",
    "우주항공": "#0369A1",
    "신재생에너지": "#047857",
}

_FALLBACK_PALETTE = [
    "#6366F1", "#8B5CF6", "#F59E0B", "#10B981",
    "#3B82F6", "#EF4444", "#14B8A6", "#F97316",
]

_TOTAL_SLOTS = 9
_INITIAL_PLACEMENT = 4   # 최초 배치 시 사용할 슬롯 수


def get_sector_color(name: str, dynamic: dict[str, str] | None = None) -> str:
    """섹터명에 대한 고유색을 반환한다."""
    if name in SECTOR_COLORS:
        return SECTOR_COLORS[name]
    if dynamic and name in dynamic:
        return dynamic[name]
    return _FALLBACK_PALETTE[abs(hash(name)) % len(_FALLBACK_PALETTE)]


# ---------------------------------------------------------------------------
# SlotManager
# ---------------------------------------------------------------------------


_GRACE_SNAPSHOTS = 3  # 연속 N회 미달일 때만 슬롯 제거 (1초 폴링 기준 3초)


class SlotManager:
    """장중 섹터 카드 고정 슬롯 관리자."""

    def __init__(self) -> None:
        self._slots: dict[int, str | None] = {i: None for i in range(1, _TOTAL_SLOTS + 1)}
        self._initialized: bool = False
        self._dynamic_colors: dict[str, str] = {}
        self._absent: dict[int, int] = {i: 0 for i in range(1, _TOTAL_SLOTS + 1)}
        """슬롯별 threshold 미달 연속 횟수. _GRACE_SNAPSHOTS 초과 시에만 제거."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def update(self, sector_views: list[IntradaySectorLeaderView]) -> None:
        """sector_views 변화에 따라 슬롯 상태를 갱신한다."""
        current_names = {sv.sector_name for sv in sector_views}

        if not self._initialized:
            self._first_ready_init(sector_views)
            return

        # 1. 탈락 섹터: grace period 초과 시에만 슬롯 비우기
        for slot_id in sorted(self._slots):
            name = self._slots[slot_id]
            if name is None:
                self._absent[slot_id] = 0
                continue
            if name not in current_names:
                self._absent[slot_id] += 1
                if self._absent[slot_id] >= _GRACE_SNAPSHOTS:
                    self._slots[slot_id] = None
                    self._absent[slot_id] = 0
            else:
                self._absent[slot_id] = 0  # 다시 나타났으면 카운트 리셋

        # 2. 신규 섹터 탐색
        assigned = {n for n in self._slots.values() if n is not None}
        new_sectors = [sv for sv in sector_views if sv.sector_name not in assigned]

        # 3. 빈 슬롯에 번호 순서대로 배치 (1 → 9)
        empty_slots = [sid for sid in sorted(self._slots) if self._slots[sid] is None]
        for sv in new_sectors:
            if not empty_slots:
                break
            slot_id = empty_slots.pop(0)
            self._slots[slot_id] = sv.sector_name
            self._ensure_dynamic_color(sv.sector_name)

    def get_slot_layout(
        self,
        sector_views: list[IntradaySectorLeaderView],
    ) -> list[dict]:
        """API 응답용 slot_layout 리스트를 반환한다.

        슬롯 1~9 를 순서대로 반환한다.
        빈 슬롯은 sector_name=None, sector=None 으로 반환한다.
        """
        sv_map = {sv.sector_name: sv for sv in sector_views}
        layout = []
        for slot_id in sorted(self._slots):
            name = self._slots[slot_id]
            sv = sv_map.get(name) if name else None

            if name is None or sv is None:
                layout.append({"slot_id": slot_id, "sector_name": None, "sector": None})
            else:
                color = get_sector_color(name, self._dynamic_colors)
                layout.append({
                    "slot_id": slot_id,
                    "sector_name": name,
                    "sector": {
                        "sector_name": sv.sector_name,
                        "leader_grade": sv.leader_grade,
                        "leader_label": sv.leader_label,
                        "strong_riser_count": sv.strong_riser_count,
                        "riser_5_count": sv.riser_5_count,
                        "sector_total_trading_value": sv.total_minute_trade_value,
                        "sector_top5_avg_change_rate": sv.sector_top5_avg_change_rate,
                        "average_change_rate": sv.average_change_rate,
                        "color": color,
                        "rank": sv.rank,
                        "leader_stocks": [
                            {
                                "rank": ls.rank,
                                "base_code": ls.base_code,
                                "stock_name": ls.stock_name,
                                "exchange": ls.exchange,
                                "close_price": ls.close_price,
                                "last_change_rate": ls.last_change_rate,
                                "minute_trade_value_delta": ls.minute_trade_value_delta,
                                "trading_value": ls.trading_value,
                                "is_high_trading_value": ls.is_high_trading_value,
                                "display_badge": ls.display_badge,
                            }
                            for ls in sv.leader_stocks
                        ],
                    },
                })
        return layout

    def reset(self) -> None:
        """슬롯 상태를 초기화한다."""
        self._slots = {i: None for i in range(1, _TOTAL_SLOTS + 1)}
        self._initialized = False
        self._dynamic_colors = {}
        self._absent = {i: 0 for i in range(1, _TOTAL_SLOTS + 1)}

    def slot_state_snapshot(self) -> dict[int, str | None]:
        """현재 슬롯 상태의 복사본을 반환한다 (디버깅/테스트용)."""
        return dict(self._slots)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _first_ready_init(self, sector_views: list[IntradaySectorLeaderView]) -> None:
        """최초 ready 시 상위 _INITIAL_PLACEMENT 개를 슬롯 1~N 에 배치한다."""
        for i in range(1, _TOTAL_SLOTS + 1):
            self._slots[i] = None
        for i, sv in enumerate(sector_views[:_INITIAL_PLACEMENT], start=1):
            self._slots[i] = sv.sector_name
            self._ensure_dynamic_color(sv.sector_name)
        self._initialized = True

    def _ensure_dynamic_color(self, name: str) -> None:
        if name not in SECTOR_COLORS and name not in self._dynamic_colors:
            idx = len(self._dynamic_colors) % len(_FALLBACK_PALETTE)
            self._dynamic_colors[name] = _FALLBACK_PALETTE[idx]
