"""v3 주도섹터 선정 정책 단위 테스트.

v3 규칙:
  - market_cap >= 500_000_000_000 종목만 후보
  - change_rate >= 10.0 인 후보를 strong_riser 로 분류
  - strong_riser_count >= 3 인 섹터만 주도섹터
  - 섹터 내 종목 목록은 change_rate 내림차순
"""
from __future__ import annotations

from src.intraday_sector_aggregator import aggregate_sector_minutes
from src.intraday_leader_ranker import SectorMinuteSummary, SectorLeaderStock, rank_intraday_leaders
from src.intraday_tick_aggregator import MinuteBucket
from src.intraday_snapshot_service import IntradaySnapshotService


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

_SECTOR_MAP = {
    "000660": ["반도체"],
    "005930": ["반도체"],
    "035420": ["반도체"],
    "066570": ["반도체"],
    "012450": ["방산"],
    "047810": ["방산"],
}

_MARKET_CAP_MAP_500B: dict[str, int] = {
    "000660": 600_000_000_000,   # 6천억 ✓
    "005930": 800_000_000_000,   # 8천억 ✓
    "035420": 550_000_000_000,   # 5.5천억 ✓
    "066570": 300_000_000_000,   # 3천억 ✗ (미만)
    "012450": 700_000_000_000,   # 7천억 ✓
    "047810": 900_000_000_000,   # 9천억 ✓
    # 저시총 종목 (map에 없음) → 자동 제외
}


def _bucket(
    base_code: str,
    last_change_rate: float | None = 1.0,
    minute_trade_value_delta: int | None = 1_000_000,
    tick_count: int = 5,
    minute_key: str = "1345",
) -> MinuteBucket:
    return MinuteBucket(
        minute_key=minute_key,
        base_code=base_code,
        exchange="sor",
        open_price=10000,
        high_price=10000,
        low_price=10000,
        close_price=10000,
        first_accumulated_trade_value=None,
        last_accumulated_trade_value=None,
        minute_trade_value_delta=minute_trade_value_delta,
        tick_count=tick_count,
        last_change_rate=last_change_rate,
        first_trade_time="134501",
        last_trade_time="134530",
    )


def _summary(
    sector_name: str = "반도체",
    strong_riser_count: int = 0,
    total_minute_trade_value: int = 5_000_000,
    rising_stock_count: int = 3,
    leader_stocks: list[SectorLeaderStock] | None = None,
) -> SectorMinuteSummary:
    if leader_stocks is None:
        leader_stocks = [
            SectorLeaderStock("000660", "sor", 10000, 1.0, 1_000_000, 5, 2_000_000.0)
        ]
    return SectorMinuteSummary(
        minute_key="1345",
        sector_name=sector_name,
        stock_count=len(leader_stocks),
        active_stock_count=len(leader_stocks),
        rising_stock_count=rising_stock_count,
        rising_ratio=rising_stock_count / max(len(leader_stocks), 1),
        average_change_rate=1.0,
        total_minute_trade_value=total_minute_trade_value,
        max_stock_trade_value=total_minute_trade_value,
        leader_stocks=leader_stocks,
        strong_riser_count=strong_riser_count,
        positive_stock_count=rising_stock_count,
    )


# ---------------------------------------------------------------------------
# 1. 시총 5천억 미만 종목은 상승률 30%여도 market_cap 필터로 제외
# ---------------------------------------------------------------------------


def test_low_market_cap_excluded_despite_high_change_rate() -> None:
    """066570: 시총 3천억(< 5천억), change_rate=30% → market_cap 필터로 제외."""
    buckets = [
        _bucket("066570", last_change_rate=30.0, minute_trade_value_delta=500_000_000),
        _bucket("000660", last_change_rate=5.0),
    ]
    result = aggregate_sector_minutes(
        buckets,
        _SECTOR_MAP,
        market_cap_map=_MARKET_CAP_MAP_500B,
    )
    sector = next((s for s in result if s.sector_name == "반도체"), None)
    # 066570은 필터돼야 함
    assert sector is not None
    codes_in_sector = {ls.base_code for ls in sector.leader_stocks}
    assert "066570" not in codes_in_sector


# ---------------------------------------------------------------------------
# 2. strong_riser 2개 섹터는 min_strong_riser_count=3 필터에서 제외
# ---------------------------------------------------------------------------


def test_sector_with_two_strong_risers_excluded() -> None:
    """strong_riser_count=2 인 섹터는 min_strong_riser_count=3 조건에서 제외."""
    s = _summary(sector_name="반도체", strong_riser_count=2)
    result = rank_intraday_leaders([s], min_strong_riser_count=3)
    assert result == []


# ---------------------------------------------------------------------------
# 3. strong_riser 3개 이상 섹터는 포함
# ---------------------------------------------------------------------------


def test_sector_with_three_strong_risers_included() -> None:
    """strong_riser_count=3 이상 섹터는 min_strong_riser_count=3 조건 통과."""
    s = _summary(sector_name="반도체", strong_riser_count=3)
    result = rank_intraday_leaders([s], min_strong_riser_count=3)
    assert len(result) == 1
    assert result[0].sector_name == "반도체"
    assert result[0].strong_riser_count == 3


# ---------------------------------------------------------------------------
# 4. 포함된 섹터 내부 종목은 상승률 내림차순
# ---------------------------------------------------------------------------


def test_leader_stocks_sorted_by_change_rate_descending() -> None:
    """aggregate 결과에서 leader_stocks는 change_rate 내림차순."""
    buckets = [
        _bucket("000660", last_change_rate=5.0, minute_trade_value_delta=200_000_000),
        _bucket("005930", last_change_rate=12.0, minute_trade_value_delta=100_000_000),
        _bucket("035420", last_change_rate=8.0, minute_trade_value_delta=300_000_000),
    ]
    result = aggregate_sector_minutes(
        buckets,
        _SECTOR_MAP,
        market_cap_map=_MARKET_CAP_MAP_500B,
    )
    leaders = result[0].leader_stocks
    rates = [ls.last_change_rate for ls in leaders if ls.last_change_rate is not None]
    assert rates == sorted(rates, reverse=True)
    assert leaders[0].base_code == "005930"   # cr=12.0 최고


# ---------------------------------------------------------------------------
# 5. change_rate None 종목은 후순위
# ---------------------------------------------------------------------------


def test_none_change_rate_sorted_last() -> None:
    """last_change_rate=None 종목은 유효 등락률 종목 뒤에 배치."""
    buckets = [
        _bucket("000660", last_change_rate=None, minute_trade_value_delta=999_999_999),
        _bucket("005930", last_change_rate=2.0, minute_trade_value_delta=1_000_000),
    ]
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)
    leaders = result[0].leader_stocks
    assert leaders[0].base_code == "005930"
    assert leaders[-1].last_change_rate is None


# ---------------------------------------------------------------------------
# 6. market_cap_map에 없는 종목은 제외
# ---------------------------------------------------------------------------


def test_code_not_in_market_cap_map_excluded() -> None:
    """market_cap_map에 없는 종목은 시가총액 불명 → 필터 제외."""
    unknown_code = "999999"
    buckets = [
        _bucket(unknown_code, last_change_rate=20.0, minute_trade_value_delta=999_000_000),
        _bucket("000660", last_change_rate=3.0),
    ]
    sm = {unknown_code: ["반도체"], "000660": ["반도체"]}
    result = aggregate_sector_minutes(
        buckets,
        sm,
        market_cap_map=_MARKET_CAP_MAP_500B,
    )
    sector = next((s for s in result if s.sector_name == "반도체"), None)
    assert sector is not None
    codes = {ls.base_code for ls in sector.leader_stocks}
    assert unknown_code not in codes


# ---------------------------------------------------------------------------
# 7. 거래대금이 매우 커도 strong_riser 조건 미충족 → 주도섹터 아님
# ---------------------------------------------------------------------------


def test_high_trade_value_without_strong_risers_not_leading() -> None:
    """거래대금 1조이지만 strong_riser_count=0 → min_strong_riser_count=3 통과 못 함."""
    rich_but_flat = _summary(
        sector_name="대형주",
        strong_riser_count=0,
        total_minute_trade_value=1_000_000_000_000,
    )
    result = rank_intraday_leaders([rich_but_flat], min_strong_riser_count=3)
    assert result == []


# ---------------------------------------------------------------------------
# 8. market_cap_map 없을 때 backward compat (모든 종목 포함, 필터 없음)
# ---------------------------------------------------------------------------


def test_no_market_cap_map_backward_compat() -> None:
    """market_cap_map 미제공 시 모든 종목이 집계에 포함된다."""
    buckets = [
        _bucket("000660", last_change_rate=15.0),
        _bucket("066570", last_change_rate=20.0),   # 시총 3천억이지만 map 없으면 포함
    ]
    sm = {"000660": ["반도체"], "066570": ["반도체"]}
    result = aggregate_sector_minutes(buckets, sm)  # market_cap_map 미전달
    assert len(result) > 0
    codes = {ls.base_code for ls in result[0].leader_stocks}
    assert "066570" in codes   # 필터 없이 포함됨


# ---------------------------------------------------------------------------
# 9. IntradaySnapshotService: market_cap_map 없으면 min_strong_riser_count=0
# ---------------------------------------------------------------------------


def test_snapshot_service_without_market_cap_map_uses_no_filter() -> None:
    """market_cap_map 미제공 서비스는 strong_riser 필터 없이 동작한다."""
    service = IntradaySnapshotService(
        sector_map={"000660": ["반도체"]},
        min_strong_riser_count=0,
    )
    assert service.min_strong_riser_count == 0
    assert service.market_cap_map == {}
