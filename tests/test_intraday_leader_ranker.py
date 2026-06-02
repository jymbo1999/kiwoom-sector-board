"""IntradayLeaderRanker 단위 테스트.

실전 WebSocket 접속 없이 순수 ViewModel 변환 로직만 테스트한다.
"""
from __future__ import annotations

import pytest

from src.intraday_leader_ranker import (
    IntradayLeaderStockView,
    IntradaySectorLeaderView,
    _compute_sector_score,
    rank_intraday_leaders,
)
from src.intraday_sector_aggregator import SectorLeaderStock, SectorMinuteSummary


# ---------------------------------------------------------------------------
# 테스트 헬퍼
# ---------------------------------------------------------------------------


def _stock(
    base_code: str = "000660",
    exchange: str = "sor",
    close_price: int | None = 70000,
    last_change_rate: float | None = 1.0,
    minute_trade_value_delta: int | None = 1_000_000,
    tick_count: int = 10,
    rank_score: float = 2_000_000.0,
) -> SectorLeaderStock:
    return SectorLeaderStock(
        base_code=base_code,
        exchange=exchange,
        close_price=close_price,
        last_change_rate=last_change_rate,
        minute_trade_value_delta=minute_trade_value_delta,
        tick_count=tick_count,
        rank_score=rank_score,
    )


def _summary(
    sector_name: str = "반도체",
    minute_key: str = "1345",
    total_minute_trade_value: int = 5_000_000,
    active_stock_count: int = 3,
    stock_count: int = 3,
    rising_stock_count: int = 2,
    rising_ratio: float | None = 0.67,
    average_change_rate: float | None = 1.0,
    max_stock_trade_value: int | None = 2_000_000,
    leader_stocks: list[SectorLeaderStock] | None = None,
    riser_5_count: int = 3,
    strong_riser_count: int = 0,
) -> SectorMinuteSummary:
    if leader_stocks is None:
        leader_stocks = [_stock()]
    return SectorMinuteSummary(
        minute_key=minute_key,
        sector_name=sector_name,
        stock_count=stock_count,
        active_stock_count=active_stock_count,
        rising_stock_count=rising_stock_count,
        rising_ratio=rising_ratio,
        average_change_rate=average_change_rate,
        total_minute_trade_value=total_minute_trade_value,
        max_stock_trade_value=max_stock_trade_value,
        leader_stocks=leader_stocks,
        riser_5_count=riser_5_count,
        strong_riser_count=strong_riser_count,
    )


# ---------------------------------------------------------------------------
# 1. 빈 summaries
# ---------------------------------------------------------------------------


def test_empty_summaries_returns_empty() -> None:
    assert rank_intraday_leaders([]) == []


# ---------------------------------------------------------------------------
# 2. 단일 섹터 랭킹
# ---------------------------------------------------------------------------


def test_single_sector_rank() -> None:
    result = rank_intraday_leaders([_summary()])
    assert len(result) == 1
    assert result[0].rank == 1
    assert result[0].sector_name == "반도체"
    assert result[0].minute_key == "1345"


# ---------------------------------------------------------------------------
# 3. 여러 섹터 sector_score 정렬
# ---------------------------------------------------------------------------


def test_multiple_sectors_sorted_by_score() -> None:
    high = _summary(
        sector_name="반도체",
        total_minute_trade_value=10_000_000,
        average_change_rate=2.0,
        rising_ratio=0.8,
        active_stock_count=5,
    )
    low = _summary(
        sector_name="조선",
        total_minute_trade_value=1_000_000,
        average_change_rate=0.5,
        rising_ratio=0.3,
        active_stock_count=2,
    )
    result = rank_intraday_leaders([low, high])
    assert result[0].sector_name == "반도체"
    assert result[1].sector_name == "조선"


# ---------------------------------------------------------------------------
# 4. sector_limit 적용
# ---------------------------------------------------------------------------


def test_sector_limit_applied() -> None:
    summaries = [_summary(sector_name=f"섹터{i}", total_minute_trade_value=i * 1_000_000)
                 for i in range(1, 8)]
    result = rank_intraday_leaders(summaries, sector_limit=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# 5. stock_limit 적용
# ---------------------------------------------------------------------------


def test_stock_limit_applied() -> None:
    stocks = [_stock(base_code=f"00066{i}") for i in range(7)]
    s = _summary(leader_stocks=stocks)
    result = rank_intraday_leaders([s], stock_limit=3)
    assert len(result[0].leader_stocks) == 3


# ---------------------------------------------------------------------------
# 6. min_total_trade_value 필터
# ---------------------------------------------------------------------------


def test_min_total_trade_value_filter() -> None:
    large = _summary(sector_name="반도체", total_minute_trade_value=5_000_000)
    small = _summary(sector_name="조선", total_minute_trade_value=100_000)
    result = rank_intraday_leaders([large, small], min_total_trade_value=1_000_000)
    assert len(result) == 1
    assert result[0].sector_name == "반도체"


# ---------------------------------------------------------------------------
# 7. min_active_stock_count 필터
# ---------------------------------------------------------------------------


def test_min_active_stock_count_filter() -> None:
    large = _summary(sector_name="반도체", active_stock_count=5)
    small = _summary(sector_name="조선", active_stock_count=1)
    result = rank_intraday_leaders([large, small], min_active_stock_count=3)
    assert len(result) == 1
    assert result[0].sector_name == "반도체"


# ---------------------------------------------------------------------------
# 8. sector rank가 1부터 부여
# ---------------------------------------------------------------------------


def test_sector_rank_starts_at_one() -> None:
    summaries = [
        _summary(sector_name="반도체", total_minute_trade_value=3_000_000),
        _summary(sector_name="조선", total_minute_trade_value=1_000_000),
    ]
    result = rank_intraday_leaders(summaries)
    assert result[0].rank == 1
    assert result[1].rank == 2


# ---------------------------------------------------------------------------
# 9. leader stock rank가 1부터 부여
# ---------------------------------------------------------------------------


def test_leader_stock_rank_starts_at_one() -> None:
    stocks = [_stock(base_code=f"00066{i}") for i in range(3)]
    result = rank_intraday_leaders([_summary(leader_stocks=stocks)])
    for i, ls in enumerate(result[0].leader_stocks, start=1):
        assert ls.rank == i


# ---------------------------------------------------------------------------
# 10. display_badge 규칙
# ---------------------------------------------------------------------------


def test_display_badge_assignment() -> None:
    stocks = [
        _stock(base_code="000660"),
        _stock(base_code="005930"),
        _stock(base_code="035420"),
        _stock(base_code="000080"),
    ]
    result = rank_intraday_leaders([_summary(leader_stocks=stocks)])
    leaders = result[0].leader_stocks
    assert leaders[0].display_badge == "대장"
    assert leaders[1].display_badge == "2등주"
    assert leaders[2].display_badge == "3등주"
    assert leaders[3].display_badge == ""


# ---------------------------------------------------------------------------
# 11. average_change_rate None → 0으로 처리
# ---------------------------------------------------------------------------


def test_average_change_rate_none_treated_as_zero_in_score() -> None:
    s_none = _summary(sector_name="A", average_change_rate=None,
                      total_minute_trade_value=1_000_000, active_stock_count=1,
                      rising_ratio=0.0)
    s_zero = _summary(sector_name="B", average_change_rate=0.0,
                      total_minute_trade_value=1_000_000, active_stock_count=1,
                      rising_ratio=0.0)
    score_none = _compute_sector_score(s_none)
    score_zero = _compute_sector_score(s_zero)
    assert score_none == pytest.approx(score_zero)


# ---------------------------------------------------------------------------
# 12. rising_ratio None → 0으로 처리
# ---------------------------------------------------------------------------


def test_rising_ratio_none_treated_as_zero_in_score() -> None:
    s_none = _summary(sector_name="A", rising_ratio=None,
                      average_change_rate=0.0, total_minute_trade_value=1_000_000,
                      active_stock_count=1)
    s_zero = _summary(sector_name="B", rising_ratio=0.0,
                      average_change_rate=0.0, total_minute_trade_value=1_000_000,
                      active_stock_count=1)
    assert _compute_sector_score(s_none) == pytest.approx(_compute_sector_score(s_zero))


# ---------------------------------------------------------------------------
# 13. leader stock의 minute_trade_value_delta None 처리
# ---------------------------------------------------------------------------


def test_leader_stock_delta_none_preserved() -> None:
    stocks = [_stock(minute_trade_value_delta=None)]
    result = rank_intraday_leaders([_summary(leader_stocks=stocks)])
    assert result[0].leader_stocks[0].minute_trade_value_delta is None


# ---------------------------------------------------------------------------
# 14. sector_score 계산 검증
# ---------------------------------------------------------------------------


def test_sector_score_calculation() -> None:
    """score = total_tv + max(avg_cr,0)*10M + (rising_ratio)*5M + active*1M."""
    s = _summary(
        total_minute_trade_value=5_000_000,
        average_change_rate=2.0,
        rising_ratio=0.5,
        active_stock_count=3,
    )
    expected = 5_000_000 + 2.0 * 10_000_000 + 0.5 * 5_000_000 + 3 * 1_000_000
    assert _compute_sector_score(s) == pytest.approx(expected)


def test_sector_score_negative_change_rate_clipped() -> None:
    """average_change_rate < 0이면 0으로 클리핑하여 score에 기여하지 않는다."""
    s = _summary(average_change_rate=-2.0, total_minute_trade_value=1_000_000,
                 rising_ratio=0.0, active_stock_count=0)
    score = _compute_sector_score(s)
    assert score == pytest.approx(1_000_000)


# ---------------------------------------------------------------------------
# 15. leader stock 필드가 원본에서 정확히 복사
# ---------------------------------------------------------------------------


def test_leader_stock_fields_copied_from_original() -> None:
    original = _stock(
        base_code="005930", exchange="nxt", close_price=55000,
        last_change_rate=2.5, minute_trade_value_delta=3_000_000,
        tick_count=20, rank_score=5_000_000.0,
    )
    result = rank_intraday_leaders([_summary(leader_stocks=[original])])
    lv = result[0].leader_stocks[0]
    assert lv.base_code == "005930"
    assert lv.exchange == "nxt"
    assert lv.close_price == 55000
    assert lv.last_change_rate == pytest.approx(2.5)
    assert lv.minute_trade_value_delta == 3_000_000
    assert lv.tick_count == 20
    assert lv.rank_score == pytest.approx(5_000_000.0)


# ---------------------------------------------------------------------------
# 16. 필터 후 아무 섹터도 없으면 빈 list
# ---------------------------------------------------------------------------


def test_all_filtered_returns_empty() -> None:
    s = _summary(total_minute_trade_value=100_000, active_stock_count=1)
    result = rank_intraday_leaders([s], min_total_trade_value=10_000_000)
    assert result == []


# ---------------------------------------------------------------------------
# 17. 동일 sector_score → total_tv 큰 섹터 우선
# ---------------------------------------------------------------------------


def test_same_score_tiebreak_by_total_tv() -> None:
    """score가 같을 때 total_minute_trade_value 큰 섹터가 앞으로 온다.

    A: total_tv=10M, avg_cr=0 → score=10M + 0 = 10M
    B: total_tv=5M, avg_cr=0.5 → score=5M + 0.5*10M = 10M  (같음)
    total_tv: A(10M) > B(5M) → A가 먼저.
    """
    a = _summary(sector_name="A", total_minute_trade_value=10_000_000,
                 average_change_rate=0.0, rising_ratio=0.0, active_stock_count=0)
    b = _summary(sector_name="B", total_minute_trade_value=5_000_000,
                 average_change_rate=0.5, rising_ratio=0.0, active_stock_count=0)
    assert _compute_sector_score(a) == pytest.approx(_compute_sector_score(b))
    result = rank_intraday_leaders([b, a], min_active_stock_count=0)
    assert result[0].sector_name == "A"


# ---------------------------------------------------------------------------
# 18. 모든 조건이 동일하면 두 섹터 모두 결과에 포함
# ---------------------------------------------------------------------------


def test_same_all_conditions_both_included() -> None:
    """grade/riser_count/tv/top5avg가 모두 같으면 두 섹터 모두 결과에 포함된다."""
    na = _summary(sector_name="나노", total_minute_trade_value=5_000_000,
                  average_change_rate=0.0, rising_ratio=0.0, active_stock_count=0)
    ga = _summary(sector_name="가전자", total_minute_trade_value=5_000_000,
                  average_change_rate=0.0, rising_ratio=0.0, active_stock_count=0)
    result = rank_intraday_leaders([na, ga], min_active_stock_count=0)
    names = {r.sector_name for r in result}
    assert "나노" in names
    assert "가전자" in names
