"""IntradaySectorAggregator 단위 테스트.

실전 WebSocket 접속 없이 순수 메모리 집계 로직만 테스트한다.
"""
from __future__ import annotations

import pytest

from src.intraday_sector_aggregator import (
    SectorLeaderStock,
    SectorMinuteSummary,
    aggregate_sector_minutes,
)
from src.intraday_tick_aggregator import MinuteBucket


# ---------------------------------------------------------------------------
# 테스트용 MinuteBucket 생성 헬퍼
# ---------------------------------------------------------------------------


def _bucket(
    base_code: str = "000660",
    exchange: str = "sor",
    minute_key: str = "1345",
    close_price: int | None = 70000,
    last_change_rate: float | None = 0.5,
    minute_trade_value_delta: int | None = 1_000_000,
    tick_count: int = 10,
) -> MinuteBucket:
    return MinuteBucket(
        minute_key=minute_key,
        base_code=base_code,
        exchange=exchange,
        open_price=close_price,
        high_price=close_price,
        low_price=close_price,
        close_price=close_price,
        first_accumulated_trade_value=None,
        last_accumulated_trade_value=None,
        minute_trade_value_delta=minute_trade_value_delta,
        tick_count=tick_count,
        last_change_rate=last_change_rate,
        first_trade_time="134501",
        last_trade_time="134530",
    )


SECTOR_MAP_BASIC: dict[str, list[str]] = {
    "000660": ["반도체"],
    "005930": ["반도체"],
    "042660": ["조선"],
}


# ---------------------------------------------------------------------------
# 1. 빈 buckets / 빈 sector_map
# ---------------------------------------------------------------------------


def test_empty_buckets_returns_empty() -> None:
    result = aggregate_sector_minutes([], SECTOR_MAP_BASIC)
    assert result == []


def test_empty_sector_map_returns_empty() -> None:
    result = aggregate_sector_minutes([_bucket()], {})
    assert result == []


# ---------------------------------------------------------------------------
# 3. 단일 종목 단일 섹터 집계
# ---------------------------------------------------------------------------


def test_single_stock_single_sector() -> None:
    buckets = [_bucket(base_code="000660", last_change_rate=1.0, minute_trade_value_delta=500_000)]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert len(result) == 1
    s = result[0]
    assert s.sector_name == "반도체"
    assert s.stock_count == 1
    assert s.minute_key == "1345"
    assert s.total_minute_trade_value == 500_000
    assert s.average_change_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. 여러 종목 같은 섹터 집계
# ---------------------------------------------------------------------------


def test_multiple_stocks_same_sector() -> None:
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=1_000_000, last_change_rate=1.0),
        _bucket(base_code="005930", minute_trade_value_delta=2_000_000, last_change_rate=2.0),
    ]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"], "005930": ["반도체"]})
    assert len(result) == 1
    s = result[0]
    assert s.stock_count == 2
    assert s.total_minute_trade_value == 3_000_000
    assert s.average_change_rate == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# 5. 여러 섹터 집계
# ---------------------------------------------------------------------------


def test_multiple_sectors() -> None:
    buckets = [
        _bucket(base_code="000660"),
        _bucket(base_code="042660"),
    ]
    result = aggregate_sector_minutes(buckets, SECTOR_MAP_BASIC)
    sector_names = {s.sector_name for s in result}
    assert sector_names == {"반도체", "조선"}


# ---------------------------------------------------------------------------
# 6. 한 종목이 여러 섹터에 중복 반영
# ---------------------------------------------------------------------------


def test_one_stock_multiple_sectors() -> None:
    sector_map = {"005930": ["반도체", "대형주"]}
    buckets = [_bucket(base_code="005930", minute_trade_value_delta=3_000_000)]
    result = aggregate_sector_minutes(buckets, sector_map)
    assert len(result) == 2
    names = {s.sector_name for s in result}
    assert names == {"반도체", "대형주"}
    for s in result:
        assert s.stock_count == 1
        assert s.total_minute_trade_value == 3_000_000


# ---------------------------------------------------------------------------
# 7. sector_map에 없는 종목 제외
# ---------------------------------------------------------------------------


def test_unmapped_stock_excluded() -> None:
    buckets = [
        _bucket(base_code="000660"),   # 매핑됨
        _bucket(base_code="999999"),   # 매핑 없음
    ]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert len(result) == 1
    assert result[0].stock_count == 1  # 999999 제외


def test_all_unmapped_returns_empty() -> None:
    buckets = [_bucket(base_code="999999")]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert result == []


# ---------------------------------------------------------------------------
# 8. minute_key 지정 시 해당 분만 집계
# ---------------------------------------------------------------------------


def test_minute_key_filter() -> None:
    buckets = [
        _bucket(base_code="000660", minute_key="1345"),
        _bucket(base_code="000660", minute_key="1346"),
    ]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]}, minute_key="1345")
    assert len(result) == 1
    assert result[0].minute_key == "1345"
    assert result[0].stock_count == 1


def test_minute_key_not_in_buckets_returns_empty() -> None:
    buckets = [_bucket(base_code="000660", minute_key="1345")]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]}, minute_key="1400")
    assert result == []


# ---------------------------------------------------------------------------
# 9. minute_key None이면 최신 분 자동 선택
# ---------------------------------------------------------------------------


def test_latest_minute_auto_selected() -> None:
    buckets = [
        _bucket(base_code="000660", minute_key="1345", minute_trade_value_delta=100),
        _bucket(base_code="000660", minute_key="1346", minute_trade_value_delta=200),
    ]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert len(result) == 1
    assert result[0].minute_key == "1346"
    assert result[0].total_minute_trade_value == 200


# ---------------------------------------------------------------------------
# 10. average_change_rate 계산
# ---------------------------------------------------------------------------


def test_average_change_rate_calculation() -> None:
    buckets = [
        _bucket(base_code="000660", last_change_rate=1.0, minute_trade_value_delta=100),
        _bucket(base_code="005930", last_change_rate=3.0, minute_trade_value_delta=100),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].average_change_rate == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 11. last_change_rate None 방어
# ---------------------------------------------------------------------------


def test_change_rate_none_excluded_from_average() -> None:
    buckets = [
        _bucket(base_code="000660", last_change_rate=2.0, minute_trade_value_delta=100),
        _bucket(base_code="005930", last_change_rate=None, minute_trade_value_delta=100),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    s = result[0]
    assert s.average_change_rate == pytest.approx(2.0)


def test_all_change_rate_none_average_is_none() -> None:
    buckets = [_bucket(base_code="000660", last_change_rate=None)]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert result[0].average_change_rate is None


# ---------------------------------------------------------------------------
# 12. total_minute_trade_value 계산
# ---------------------------------------------------------------------------


def test_total_trade_value_sum() -> None:
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=1_000_000),
        _bucket(base_code="005930", minute_trade_value_delta=4_000_000),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].total_minute_trade_value == 5_000_000


# ---------------------------------------------------------------------------
# 13. minute_trade_value_delta None이면 0 처리
# ---------------------------------------------------------------------------


def test_delta_none_treated_as_zero_in_total() -> None:
    """delta None 종목은 total_minute_trade_value 합산에서 0으로 취급한다."""
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=2_000_000),
        _bucket(base_code="005930", minute_trade_value_delta=None),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].total_minute_trade_value == 2_000_000


# ---------------------------------------------------------------------------
# 14. rising_stock_count 계산
# ---------------------------------------------------------------------------


def test_rising_stock_count() -> None:
    buckets = [
        _bucket(base_code="000660", last_change_rate=1.0, minute_trade_value_delta=100),
        _bucket(base_code="005930", last_change_rate=-0.5, minute_trade_value_delta=100),
        _bucket(base_code="035420", last_change_rate=0.0, minute_trade_value_delta=100),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"], "035420": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].rising_stock_count == 1  # change > 0인 종목만


# ---------------------------------------------------------------------------
# 15. rising_ratio 계산
# ---------------------------------------------------------------------------


def test_rising_ratio_calculation() -> None:
    buckets = [
        _bucket(base_code="000660", last_change_rate=1.0, minute_trade_value_delta=100),
        _bucket(base_code="005930", last_change_rate=-0.5, minute_trade_value_delta=100),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].rising_ratio == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 16. rising_ratio 분모가 0이면 None
# ---------------------------------------------------------------------------


def test_rising_ratio_none_when_all_change_rate_none() -> None:
    """last_change_rate가 모두 None이면 rising_ratio = None."""
    buckets = [
        _bucket(base_code="000660", last_change_rate=None, minute_trade_value_delta=100),
    ]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    assert result[0].rising_ratio is None


# ---------------------------------------------------------------------------
# 17. leader_stocks limit 적용
# ---------------------------------------------------------------------------


def test_leader_stocks_limit() -> None:
    buckets = [
        _bucket(base_code=f"00066{i}", minute_trade_value_delta=i * 100)
        for i in range(1, 8)
    ]
    sm = {f"00066{i}": ["반도체"] for i in range(1, 8)}
    result = aggregate_sector_minutes(buckets, sm, leader_limit=3)
    assert len(result[0].leader_stocks) == 3


# ---------------------------------------------------------------------------
# 18. leader_stocks 정렬 기준 검증
# ---------------------------------------------------------------------------


def test_leader_stocks_sorted_by_delta_desc() -> None:
    """delta 큰 순 → change_rate 큰 순 → tick_count 큰 순."""
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=500, last_change_rate=1.0, tick_count=5),
        _bucket(base_code="005930", minute_trade_value_delta=1000, last_change_rate=0.5, tick_count=3),
        _bucket(base_code="035420", minute_trade_value_delta=500, last_change_rate=2.0, tick_count=8),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"], "035420": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm, leader_limit=5)
    leaders = result[0].leader_stocks
    # 1위: 005930 (delta=1000)
    assert leaders[0].base_code == "005930"
    # 2위: 035420 (delta=500, change=2.0) vs 000660 (delta=500, change=1.0)
    assert leaders[1].base_code == "035420"
    assert leaders[2].base_code == "000660"


def test_leader_stocks_delta_none_sorted_last() -> None:
    """delta None은 후순위로 정렬된다."""
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=None),
        _bucket(base_code="005930", minute_trade_value_delta=500),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm, leader_limit=5)
    leaders = result[0].leader_stocks
    assert leaders[0].base_code == "005930"
    assert leaders[-1].minute_trade_value_delta is None


# ---------------------------------------------------------------------------
# 19. rank_score 계산 검증
# ---------------------------------------------------------------------------


def test_rank_score_formula() -> None:
    """rank_score = (delta or 0) + max(change_rate, 0) * 1_000_000."""
    buckets = [_bucket(base_code="000660", minute_trade_value_delta=2_000_000, last_change_rate=1.5)]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    leader = result[0].leader_stocks[0]
    expected = 2_000_000 + 1.5 * 1_000_000
    assert leader.rank_score == pytest.approx(expected)


def test_rank_score_negative_change_rate_clipped() -> None:
    """change_rate < 0이면 rank_score에 기여하지 않는다."""
    buckets = [_bucket(base_code="000660", minute_trade_value_delta=1_000_000, last_change_rate=-2.0)]
    result = aggregate_sector_minutes(buckets, {"000660": ["반도체"]})
    leader = result[0].leader_stocks[0]
    assert leader.rank_score == pytest.approx(1_000_000)


# ---------------------------------------------------------------------------
# 20. sector summary 정렬 기준 검증
# ---------------------------------------------------------------------------


def test_sector_summary_sorted_by_total_trade_value() -> None:
    """total_minute_trade_value 큰 섹터가 앞으로 정렬된다."""
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=5_000_000, last_change_rate=1.0),
        _bucket(base_code="042660", minute_trade_value_delta=1_000_000, last_change_rate=2.0),
    ]
    sm = {"000660": ["반도체"], "042660": ["조선"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].sector_name == "반도체"   # tv=5M > tv=1M
    assert result[1].sector_name == "조선"


def test_sector_summary_tiebreak_by_average_change_rate() -> None:
    """total_tv 동일 시 average_change_rate 큰 섹터가 앞으로."""
    buckets = [
        _bucket(base_code="000660", minute_trade_value_delta=1_000_000, last_change_rate=1.0),
        _bucket(base_code="042660", minute_trade_value_delta=1_000_000, last_change_rate=3.0),
    ]
    sm = {"000660": ["반도체"], "042660": ["조선"]}
    result = aggregate_sector_minutes(buckets, sm)
    assert result[0].sector_name == "조선"   # avg_cr=3.0 > 1.0
