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
    trading_value: int | None = None
    is_high_trading_value: bool = False


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
    strong_riser_count: int = 0           # v3/v4: change_rate >= 10.0 종목 수
    riser_5_count: int = 0               # v4: change_rate >= 5.0 종목 수
    top3_avg_change_rate: float = 0.0    # v3: 상위 3종목 평균 상승률
    sector_top5_avg_change_rate: float = 0.0  # v4: 상위 5종목 평균 상승률
    leader_grade: str = ""               # v4: "A", "B", "C"
    leader_label: str = ""               # v4: "강한 주도섹터", "주도섹터", "관심섹터"
    market_cap_filter_min: int = 0       # 적용된 시가총액 하한선(0=필터 없음)
    leadership_rule: str = ""            # 선정 규칙 식별자


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


_GRADE_RANK = {"A": 3, "B": 2, "C": 1}


def _compute_leader_grade(strong_riser_count: int) -> tuple[str, str]:
    """strong_riser_count(10%↑ 종목 수)로 A/B/C 등급을 반환한다."""
    if strong_riser_count >= 3:
        return "A", "강한 주도섹터"
    if strong_riser_count >= 1:
        return "B", "주도섹터"
    return "C", "관심섹터"


def _sector_sort_key(v: IntradaySectorLeaderView) -> tuple:
    """v4: grade(A>B>C) → strong_10_count → riser_5_count → total_tv → top5_avg."""
    return (
        -_GRADE_RANK.get(v.leader_grade, 0),
        -v.strong_riser_count,
        -v.riser_5_count,
        -v.total_minute_trade_value,
        -v.sector_top5_avg_change_rate,
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
    min_riser_count: int = 3,
    market_cap_filter_min: int = 0,
    leadership_rule: str = "",
    # v3 호환 파라미터 (무시됨)
    min_strong_riser_count: int = 0,
) -> list[IntradaySectorLeaderView]:
    """SectorMinuteSummary 리스트를 받아 주도섹터 랭킹 ViewModel을 반환한다 (v4).

    표시 조건: riser_5_count(+5%↑ 종목 수) >= min_riser_count (기본 3)
    강도 등급: strong_riser_count(+10%↑ 종목 수) 기준 A/B/C

    Returns:
        v4 정렬 기준(grade → 10%↑ → 5%↑ → 거래대금 → top5avg)으로 정렬된 리스트.
    """
    if not summaries:
        return []

    filtered = [
        s for s in summaries
        if s.total_minute_trade_value >= min_total_trade_value
        and s.active_stock_count >= min_active_stock_count
        and s.riser_5_count >= min_riser_count
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

        # is_high_trading_value: 섹터 내 거래대금 상위 3개 종목
        sorted_by_tv = sorted(
            leaders,
            key=lambda ls: ls.minute_trade_value_delta or 0,
            reverse=True,
        )
        high_tv_codes = {ls.base_code for ls in sorted_by_tv[:3] if ls.minute_trade_value_delta}
        for ls in leaders:
            ls.trading_value = ls.minute_trade_value_delta
            ls.is_high_trading_value = ls.base_code in high_tv_codes

        top3_rates = [
            ls.last_change_rate
            for ls in summary.leader_stocks[:3]
            if ls.last_change_rate is not None
        ]
        top3_avg = sum(top3_rates) / len(top3_rates) if top3_rates else 0.0

        top5_rates = [
            ls.last_change_rate
            for ls in summary.leader_stocks[:5]
            if ls.last_change_rate is not None
        ]
        top5_avg = sum(top5_rates) / len(top5_rates) if top5_rates else 0.0

        grade, label = _compute_leader_grade(summary.strong_riser_count)

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
            riser_5_count=summary.riser_5_count,
            top3_avg_change_rate=top3_avg,
            sector_top5_avg_change_rate=top5_avg,
            leader_grade=grade,
            leader_label=label,
            market_cap_filter_min=market_cap_filter_min,
            leadership_rule=leadership_rule,
        ))

    views.sort(key=_sector_sort_key)
    views = views[:sector_limit]
    for i, view in enumerate(views, start=1):
        view.rank = i
    return views
