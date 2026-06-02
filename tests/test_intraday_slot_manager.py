"""src/intraday_slot_manager.py 단위 테스트.

고정 슬롯 배치 시스템의 핵심 규칙을 검증한다:
  1. 최초 ready 시 상위 4개만 슬롯 1~4에 배치, 5~9는 empty
  2. 점수 순위 변동으로 슬롯 위치 재정렬 없음
  3. 탈락 섹터는 해당 슬롯만 None, 다른 슬롯 앞당김 없음
  4. 신규 섹터는 빈 슬롯 번호 순서대로 배치
  5. 1~6 슬롯 모두 찰 경우 7~9 확장 슬롯 사용
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Minimal stub for IntradaySectorLeaderView (테스트 격리)
# ---------------------------------------------------------------------------


@dataclass
class _SV:
    """IntradaySectorLeaderView 의 테스트 전용 스텁."""
    sector_name: str
    rank: int = 0
    leader_grade: str = "C"
    leader_label: str = "관심섹터"
    strong_riser_count: int = 0
    riser_5_count: int = 3
    total_minute_trade_value: int = 1_000_000_000
    sector_top5_avg_change_rate: float = 5.0
    average_change_rate: float = 5.0
    leader_stocks: list = field(default_factory=list)


def _views(*names: str) -> list[_SV]:
    return [_SV(sector_name=n, rank=i + 1) for i, n in enumerate(names)]


# ---------------------------------------------------------------------------
# 1. 최초 배치 (first_ready_init)
# ---------------------------------------------------------------------------


def test_first_ready_places_top4_in_slots_1_to_4():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선"))
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"
    assert state[2] == "반도체"
    assert state[3] == "바이오"
    assert state[4] == "전력기기"


def test_first_ready_slots_5_to_9_are_empty():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선"))
    state = sm.slot_state_snapshot()
    for slot_id in range(5, 10):
        assert state[slot_id] is None, f"slot {slot_id} should be empty after first ready"


def test_first_ready_with_fewer_than_4_sectors():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체"))
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"
    assert state[2] == "반도체"
    assert state[3] is None
    assert state[4] is None


def test_is_initialized_false_before_first_update():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    assert not sm.is_initialized


def test_is_initialized_true_after_first_update():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇"))
    assert sm.is_initialized


# ---------------------------------------------------------------------------
# 2. 슬롯 고정 (순위 변동에도 재정렬 없음)
# ---------------------------------------------------------------------------


def test_rank_change_does_not_reorder_slots():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    # 초기: 로봇 1등, 반도체 2등
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 반도체가 1등이 되어도 슬롯 위치 유지
    sm.update(_views("반도체", "로봇", "바이오", "전력기기"))
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"
    assert state[2] == "반도체"


def test_existing_sectors_stay_in_place_across_multiple_updates():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    for _ in range(5):
        sm.update(_views("전력기기", "바이오", "반도체", "로봇"))  # 역순
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"
    assert state[2] == "반도체"
    assert state[3] == "바이오"
    assert state[4] == "전력기기"


# ---------------------------------------------------------------------------
# 3. 섹터 탈락 (해당 슬롯만 None, 앞당김 없음)
# ---------------------------------------------------------------------------


def test_dropped_sector_clears_only_its_slot():
    from src.intraday_slot_manager import SlotManager, _GRACE_SNAPSHOTS
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 로봇 탈락 — grace period 채워야 비워짐
    without_robot = _views("반도체", "바이오", "전력기기")
    for _ in range(_GRACE_SNAPSHOTS):
        sm.update(without_robot)
    state = sm.slot_state_snapshot()
    assert state[1] is None     # 로봇이 있던 슬롯만 비워짐
    assert state[2] == "반도체"  # 앞으로 당기지 않음
    assert state[3] == "바이오"
    assert state[4] == "전력기기"


def test_dropped_sector_not_cleared_before_grace_period():
    from src.intraday_slot_manager import SlotManager, _GRACE_SNAPSHOTS
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # grace period 미만 — 슬롯 유지
    without_robot = _views("반도체", "바이오", "전력기기")
    for _ in range(_GRACE_SNAPSHOTS - 1):
        sm.update(without_robot)
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"  # 아직 비워지지 않음


def test_multiple_sectors_drop_independently():
    from src.intraday_slot_manager import SlotManager, _GRACE_SNAPSHOTS
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 반도체, 전력기기 탈락 — grace period 채우기
    only_robot_bio = _views("로봇", "바이오")
    for _ in range(_GRACE_SNAPSHOTS):
        sm.update(only_robot_bio)
    state = sm.slot_state_snapshot()
    assert state[1] == "로봇"
    assert state[2] is None
    assert state[3] == "바이오"
    assert state[4] is None


# ---------------------------------------------------------------------------
# 4. 신규 섹터 진입 (빈 슬롯 번호 순서대로)
# ---------------------------------------------------------------------------


def test_new_sector_fills_first_empty_slot():
    from src.intraday_slot_manager import SlotManager, _GRACE_SNAPSHOTS
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 로봇 탈락 + 조선 신규 진입
    # grace period 동안 슬롯1은 로봇 유지 → 조선은 빈 슬롯5에 즉시 배치
    without_robot_with_joseon = _views("반도체", "바이오", "전력기기", "조선")
    for _ in range(_GRACE_SNAPSHOTS):
        sm.update(without_robot_with_joseon)
    state = sm.slot_state_snapshot()
    assert state[1] is None    # grace period 후 로봇 자리 비워짐
    assert state[5] == "조선"  # 조선은 grace period 중 슬롯5(첫 빈 슬롯)에 배치됨


def test_new_sector_fills_slot_5_after_initial_4():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 조선이 신규 진입 (5번 슬롯이 비어 있음)
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선"))
    state = sm.slot_state_snapshot()
    assert state[5] == "조선"
    assert state[6] is None


def test_multiple_new_sectors_fill_slots_in_order():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선", "방산"))
    state = sm.slot_state_snapshot()
    assert state[5] == "조선"
    assert state[6] == "방산"


def test_new_sector_uses_extension_slots_7_to_9():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    # 슬롯 5~6 채우기
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선", "방산"))
    # 슬롯 7 채우기
    sm.update(_views("로봇", "반도체", "바이오", "전력기기", "조선", "방산", "AI"))
    state = sm.slot_state_snapshot()
    assert state[7] == "AI"
    assert state[8] is None
    assert state[9] is None


# ---------------------------------------------------------------------------
# 5. get_slot_layout 구조 검증
# ---------------------------------------------------------------------------


def test_get_slot_layout_returns_9_slots():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체"))
    layout = sm.get_slot_layout(_views("로봇", "반도체"))
    assert len(layout) == 9


def test_get_slot_layout_slot_ids_are_1_to_9():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇"))
    layout = sm.get_slot_layout(_views("로봇"))
    assert [s["slot_id"] for s in layout] == list(range(1, 10))


def test_get_slot_layout_filled_slot_has_sector():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체"))
    layout = sm.get_slot_layout(_views("로봇", "반도체"))
    s1 = layout[0]
    assert s1["sector_name"] == "로봇"
    assert s1["sector"] is not None
    assert s1["sector"]["sector_name"] == "로봇"


def test_get_slot_layout_empty_slot_has_null_sector():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇"))
    layout = sm.get_slot_layout(_views("로봇"))
    s5 = layout[4]
    assert s5["sector_name"] is None
    assert s5["sector"] is None


def test_get_slot_layout_sector_has_color():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇"))
    layout = sm.get_slot_layout(_views("로봇"))
    assert layout[0]["sector"]["color"] == "#7C3AED"


def test_get_slot_layout_unknown_sector_gets_fallback_color():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sv = _views("알수없는섹터")
    sm.update(sv)
    layout = sm.get_slot_layout(sv)
    color = layout[0]["sector"]["color"]
    assert color.startswith("#")
    assert len(color) == 7


# ---------------------------------------------------------------------------
# 6. reset
# ---------------------------------------------------------------------------


def test_reset_clears_all_slots():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    sm.reset()
    state = sm.slot_state_snapshot()
    assert all(v is None for v in state.values())


def test_reset_allows_fresh_initialization():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇", "반도체", "바이오", "전력기기"))
    sm.update(_views("반도체"))  # 장중 업데이트
    sm.reset()
    # 재초기화: 다시 first_ready_init 동작
    sm.update(_views("조선", "방산"))
    state = sm.slot_state_snapshot()
    assert state[1] == "조선"
    assert state[2] == "방산"
    assert not sm.is_initialized is False  # is_initialized == True after update


def test_reset_is_not_initialized():
    from src.intraday_slot_manager import SlotManager
    sm = SlotManager()
    sm.update(_views("로봇"))
    sm.reset()
    assert not sm.is_initialized


# ---------------------------------------------------------------------------
# 7. snapshot_to_dict 에 slot_layout 포함 여부
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_includes_slot_layout():
    from src.intraday_snapshot_service import IntradaySnapshotService
    from src.intraday_snapshot_serialization import snapshot_to_dict

    sm = {"000660": ["반도체"], "005930": ["반도체"], "000270": ["자동차"],
          "051910": ["화학"], "068270": ["바이오"]}
    svc = IntradaySnapshotService(sm, min_riser_count=0)
    rows = [
        {"base_code": "000660", "exchange": "sor", "trade_time": "134501",
         "current_price": 70000, "change_rate": 6.0,
         "accumulated_trade_value": 5_000_000_000, "accumulated_volume": 100000},
        {"base_code": "005930", "exchange": "sor", "trade_time": "134501",
         "current_price": 81000, "change_rate": 5.5,
         "accumulated_trade_value": 8_000_000_000, "accumulated_volume": 200000},
    ]
    svc.ingest_rows(rows)
    snap = svc.get_snapshot()
    d = snapshot_to_dict(snap)

    assert "slot_layout" in d
    assert isinstance(d["slot_layout"], list)


def test_snapshot_slot_layout_has_9_entries_when_ready():
    from src.intraday_snapshot_service import IntradaySnapshotService
    from src.intraday_snapshot_serialization import snapshot_to_dict

    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    svc = IntradaySnapshotService(sm, min_riser_count=0)
    svc.ingest_rows([
        {"base_code": "000660", "exchange": "sor", "trade_time": "134501",
         "current_price": 70000, "change_rate": 6.0,
         "accumulated_trade_value": 5_000_000_000, "accumulated_volume": 100000},
    ])
    snap = svc.get_snapshot()
    if snap.status == "ready":
        d = snapshot_to_dict(snap)
        assert len(d["slot_layout"]) == 9
