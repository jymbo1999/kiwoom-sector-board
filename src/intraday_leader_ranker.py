"""장중 주도섹터/대장주 랭킹 ViewModel 생성 모듈.

SectorMinuteSummary 리스트를 받아 대시보드에 바로 표시할 수 있는
IntradaySectorLeaderView 리스트를 만든다.

DB 저장, Flask UI, 실제 WebSocket 실행과 무관한 순수 메모리 변환 레이어.
아직 intraday_snapshot_service.py 또는 Flask collector에 연결하지 않았다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .intraday_sector_aggregator import SectorLeaderStock, SectorMinuteSummary


# ---------------------------------------------------------------------------
# View dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IntradayLeaderStockView:
    """섹터 내 대장주 ViewModel."""

    rank: int
    base_code: str
    exchange: str
    close_price: int | None
    last_change_rate: float | None
    minute_trade_value_delta: int | None
    tick_count: int
    rank_score: float
    display_badge: str
    """rank에 따라 부여: 1='대장', 2='2등주', 3='3등주', 그 외=''."""
    stock_name: str = ""


@dataclass
class IntradaySectorLeaderView:
    """장중 주도섹터 ViewModel."""

    rank: int
    minute_key: str
    sector_name: str
    stock_count: int
    active_stock_count: int
    rising_stock_count: int
    rising_ratio: float | None
    average_change_rate: float | None
    total_minute_trade_value: int
    sector_score: float
    leader_stocks: list[IntradayLeaderStockView]
    strong_riser_count: int = 0           # v3: change_rate >= 10.0 종목 수
    top3_avg_change_rate: float = 0.0    # v3: 상위 3종목 평균 상승률
    market_cap_filter_min: int = 0       # 적용된 시가총액 하한선(0=필터 없음)
    leadership_rule: str = ""            # v3 선정 규칙 식별자


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _compute_sector_score(summary: SectorMinuteSummary) -> float:
    """섹터 score 계산 (임시 v1).

    구성 요소:
      trade_component    = total_minute_trade_value
      change_component   = max(average_change_rate, 0) * 10_000_000
      breadth_component  = (rising_ratio or 0) * 5_000_000
      activity_component = active_stock_count * 1_000_000

    향후 개선 예정:
      - 시장 평균 대비 초과수익률 반영
      - 섹터별 기준 거래대금으로 정규화
      - 컴포넌트 가중치 조정
    """
    trade = summary.total_minute_trade_value
    change = max(summary.average_change_rate or 0, 0) * 10_000_000
    breadth = (summary.rising_ratio or 0) * 5_000_000
    activity = summary.active_stock_count * 1_000_000
    return trade + change + breadth + activity


def _display_badge(rank: int) -> str:
    if rank == 1:
        return "대장"
    if rank == 2:
        return "2등주"
    if rank == 3:
        return "3등주"
    return ""


def _make_stock_view(stock: SectorLeaderStock, rank: int) -> IntradayLeaderStockView:
    return IntradayLeaderStockView(
        rank=rank,
        base_code=stock.base_code,
        exchange=stock.exchange,
        close_price=stock.close_price,
        last_change_rate=stock.last_change_rate,
        minute_trade_value_delta=stock.minute_trade_value_delta,
        tick_count=stock.tick_count,
        rank_score=stock.rank_score,
        display_badge=_display_badge(rank),
    )


def _sector_sort_key(v: IntradaySectorLeaderView) -> tuple:
    """v3: strong_riser_count 내림 → top3_avg 내림 → total_tv 내림 → rising_stock_count 내림 → sector_name 오름."""
    return (
        -v.strong_riser_count,
        -v.top3_avg_change_rate,
        -v.total_minute_trade_value,
        -v.rising_stock_count,
        v.sector_name,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rank_intraday_leaders(
    summaries: list[SectorMinuteSummary],
    sector_limit: int = 5,
    stock_limit: int = 5,
    min_total_trade_value: int = 0,
    min_active_stock_count: int = 1,
    min_strong_riser_count: int = 0,
    market_cap_filter_min: int = 0,
    leadership_rule: str = "",
) -> list[IntradaySectorLeaderView]:
    """SectorMinuteSummary 리스트를 받아 주도섹터 랭킹 ViewModel을 반환한다.

    Args:
        summaries:              aggregate_sector_minutes() 결과.
        sector_limit:           반환할 최대 섹터 수. 기본 5.
        stock_limit:            섹터당 표시할 최대 대장주 수. 기본 5.
        min_total_trade_value:  이 값 미만 total_minute_trade_value 섹터 제외.
        min_active_stock_count: 이 값 미만 active_stock_count 섹터 제외.
        min_strong_riser_count: v3: 이 값 미만 strong_riser_count 섹터 제외. 기본 0(비활성).
        market_cap_filter_min:  ViewModel에 기록할 시가총액 하한선.
        leadership_rule:        ViewModel에 기록할 선정 규칙 식별자.

    Returns:
        v3 정렬 기준으로 정렬된 IntradaySectorLeaderView 리스트.
        summaries가 비어 있거나 필터 후 남은 섹터가 없으면 빈 리스트.
    """
    if not summaries:
        return []

    filtered = [
        s for s in summaries
        if s.total_minute_trade_value >= min_total_trade_value
        and s.active_stock_count >= min_active_stock_count
        and s.strong_riser_count >= min_strong_riser_count
    ]
    if not filtered:
        return []

    views: list[IntradaySectorLeaderView] = []
    for summary in filtered:
        score = _compute_sector_score(summary)
        leaders = [
            _make_stock_view(stock, rank)
            for rank, stock in enumerate(summary.leader_stocks[:stock_limit], start=1)
        ]
        top3_rates = [
            ls.last_change_rate
            for ls in summary.leader_stocks[:3]
            if ls.last_change_rate is not None
        ]
        top3_avg = sum(top3_rates) / len(top3_rates) if top3_rates else 0.0
        views.append(IntradaySectorLeaderView(
            rank=0,
            minute_key=summary.minute_key,
            sector_name=summary.sector_name,
            stock_count=summary.stock_count,
            active_stock_count=summary.active_stock_count,
            rising_stock_count=summary.rising_stock_count,
            rising_ratio=summary.rising_ratio,
            average_change_rate=summary.average_change_rate,
            total_minute_trade_value=summary.total_minute_trade_value,
            sector_score=score,
            leader_stocks=leaders,
            strong_riser_count=summary.strong_riser_count,
            top3_avg_change_rate=top3_avg,
            market_cap_filter_min=market_cap_filter_min,
            leadership_rule=leadership_rule,
        ))

    views.sort(key=_sector_sort_key)
    views = views[:sector_limit]
    for i, view in enumerate(views, start=1):
        view.rank = i
    return views
