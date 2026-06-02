"""섹터별 실시간 분 단위 집계 모듈.

IntradayTickAggregator가 생성한 MinuteBucket 리스트와
외부에서 주입받은 sector_map을 결합해 섹터별 집계 요약을 만든다.

DB 저장, Flask UI, 실제 WebSocket 실행과 무관한 순수 메모리 집계 레이어.
아직 운영 흐름(collector, snapshot service)에 연결하지 않았다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .intraday_tick_aggregator import MinuteBucket


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SectorLeaderStock:
    """섹터 내 대장주 후보 종목."""

    base_code: str
    exchange: str
    close_price: int | None
    last_change_rate: float | None
    minute_trade_value_delta: int | None
    tick_count: int
    rank_score: float
    """임시 v1 점수 = (delta or 0) + max(change_rate, 0) * 1_000_000.
    향후 정규화/가중치 조정 예정.
    """


@dataclass
class SectorMinuteSummary:
    """분 단위 섹터 집계 요약.

    minute_trade_value_delta가 None인 종목은 total_minute_trade_value 계산에서
    0으로 취급한다. (delta None 종목도 섹터에 포함되어 있다는 사실은 보존)
    """

    minute_key: str
    sector_name: str
    stock_count: int                     # 해당 분에 bucket이 있는 종목 수
    active_stock_count: int              # tick_count > 0인 종목 수 (현재 stock_count와 동일)
    rising_stock_count: int
    rising_ratio: float | None           # 분모가 0이면 None
    average_change_rate: float | None    # last_change_rate None 종목은 평균 제외
    total_minute_trade_value: int        # delta None → 0으로 합산
    max_stock_trade_value: int | None
    leader_stocks: list[SectorLeaderStock]
    strong_riser_count: int = 0          # v3: change_rate >= 10.0 종목 수
    positive_stock_count: int = 0        # change_rate > 0 종목 수


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _rank_score(bucket: MinuteBucket) -> float:
    """임시 v1 rank score. 향후 정규화/가중치 조정 예정."""
    tv = bucket.minute_trade_value_delta or 0
    cr = max(bucket.last_change_rate or 0, 0)
    return tv + cr * 1_000_000


def _leader_sort_key(stock: SectorLeaderStock) -> tuple:
    """v3: change_rate 내림 → delta 내림 → tick_count 내림."""
    return (
        stock.last_change_rate is None,
        -(stock.last_change_rate or 0),
        stock.minute_trade_value_delta is None,
        -(stock.minute_trade_value_delta or 0),
        -stock.tick_count,
    )


def _summary_sort_key(s: SectorMinuteSummary) -> tuple:
    """섹터 summary 정렬: total_tv 내림 → avg_change_rate 내림 → rising_ratio 내림."""
    return (
        -s.total_minute_trade_value,
        s.average_change_rate is None,
        -(s.average_change_rate or 0),
        s.rising_ratio is None,
        -(s.rising_ratio or 0),
    )


def _make_leader(bucket: MinuteBucket) -> SectorLeaderStock:
    return SectorLeaderStock(
        base_code=bucket.base_code,
        exchange=bucket.exchange,
        close_price=bucket.close_price,
        last_change_rate=bucket.last_change_rate,
        minute_trade_value_delta=bucket.minute_trade_value_delta,
        tick_count=bucket.tick_count,
        rank_score=_rank_score(bucket),
    )


_STRONG_RISER_THRESHOLD = 10.0


def _build_summary(
    sector_name: str,
    minute_key: str,
    buckets: list[MinuteBucket],
    leader_limit: int,
) -> SectorMinuteSummary:
    stock_count = len(buckets)
    active_stock_count = stock_count  # 모든 bucket은 tick_count >= 1

    # 등락률 집계 — None 제외
    rated = [b for b in buckets if b.last_change_rate is not None]
    avg_cr: float | None = (
        sum(b.last_change_rate for b in rated) / len(rated) if rated else None  # type: ignore[misc]
    )

    # 상승/강세 종목 수
    rising = [b for b in rated if b.last_change_rate > 0]  # type: ignore[operator]
    rising_stock_count = len(rising)
    rising_ratio: float | None = len(rising) / len(rated) if rated else None
    strong_riser_count = sum(
        1 for b in rated if (b.last_change_rate or 0) >= _STRONG_RISER_THRESHOLD
    )
    positive_stock_count = rising_stock_count

    # 거래대금 — delta None은 0으로 취급
    total_tv = sum(b.minute_trade_value_delta or 0 for b in buckets)
    tv_vals = [b.minute_trade_value_delta for b in buckets if b.minute_trade_value_delta is not None]
    max_tv: int | None = max(tv_vals) if tv_vals else None

    # 대장주 (v3: change_rate 내림차순)
    leaders = sorted([_make_leader(b) for b in buckets], key=_leader_sort_key)[:leader_limit]

    return SectorMinuteSummary(
        minute_key=minute_key,
        sector_name=sector_name,
        stock_count=stock_count,
        active_stock_count=active_stock_count,
        rising_stock_count=rising_stock_count,
        rising_ratio=rising_ratio,
        average_change_rate=avg_cr,
        total_minute_trade_value=total_tv,
        max_stock_trade_value=max_tv,
        leader_stocks=leaders,
        strong_riser_count=strong_riser_count,
        positive_stock_count=positive_stock_count,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


MARKET_CAP_MIN_DEFAULT = 500_000_000_000


def aggregate_sector_minutes(
    buckets: list[MinuteBucket],
    sector_map: dict[str, list[str]],
    minute_key: str | None = None,
    leader_limit: int = 5,
    market_cap_map: dict[str, int] | None = None,
    market_cap_min: int = MARKET_CAP_MIN_DEFAULT,
) -> list[SectorMinuteSummary]:
    """MinuteBucket 리스트와 sector_map을 결합해 섹터별 분 단위 집계를 반환한다.

    Args:
        buckets:         IntradayTickAggregator.get_minute_buckets() 결과.
        sector_map:      base_code → 섹터명 리스트.
                         한 종목이 여러 섹터에 속하면 각 섹터에 중복 반영.
        minute_key:      집계 대상 분(HHMM). None이면 buckets 내 최신 분 자동 선택.
        leader_limit:    섹터당 대장주 수. 기본 5.
        market_cap_map:  base_code → 시가총액(원). 제공 시 market_cap_min 미만 종목 제외.
                         None 또는 빈 dict이면 필터 없이 전 종목 사용.
        market_cap_min:  시가총액 하한선. 기본 500_000_000_000(5천억).

    Returns:
        total_minute_trade_value 내림차순으로 정렬된 SectorMinuteSummary 리스트.
        buckets 또는 sector_map이 비어 있으면 빈 리스트.
    """
    if not buckets or not sector_map:
        return []

    target = minute_key if minute_key is not None else max(b.minute_key for b in buckets)

    filtered = [b for b in buckets if b.minute_key == target]
    if not filtered:
        return []

    # v3: market_cap_map이 있으면 시가총액 기준 필터 적용
    if market_cap_map:
        filtered = [
            b for b in filtered
            if (market_cap_map.get(b.base_code) or 0) >= market_cap_min
        ]
    if not filtered:
        return []

    # 섹터별 bucket 그룹화 (한 종목 → 여러 섹터 중복 허용)
    sector_buckets: dict[str, list[MinuteBucket]] = {}
    for bucket in filtered:
        sectors = sector_map.get(bucket.base_code)
        if not sectors:
            continue
        for sector in sectors:
            sector_buckets.setdefault(sector, []).append(bucket)

    if not sector_buckets:
        return []

    summaries = [
        _build_summary(sector_name, target, bkts, leader_limit)
        for sector_name, bkts in sector_buckets.items()
    ]
    summaries.sort(key=_summary_sort_key)
    return summaries
