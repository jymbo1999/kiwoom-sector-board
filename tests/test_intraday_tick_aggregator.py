"""IntradayTickAggregator 단위 테스트.

실전 WebSocket 접속 없이 순수 메모리 집계 로직만 테스트한다.
"""
from __future__ import annotations

import pytest

from src.intraday_tick_aggregator import (
    IntradayTickAggregator,
    LatestTickState,
    MinuteBucket,
    _parse_minute_key,
    _recalculate_delta,
)


# ---------------------------------------------------------------------------
# 테스트용 row 생성 헬퍼
# ---------------------------------------------------------------------------


def _row(
    base_code: str = "000660",
    exchange: str = "sor",
    trade_time: str | None = "134501",
    current_price: int | None = 70000,
    change_rate: float | None = 0.5,
    accumulated_volume: int | None = 1_000_000,
    accumulated_trade_value: int | None = 70_000_000_000,
) -> dict:
    return {
        "base_code": base_code,
        "exchange": exchange,
        "trade_time": trade_time,
        "current_price": current_price,
        "change_rate": change_rate,
        "accumulated_volume": accumulated_volume,
        "accumulated_trade_value": accumulated_trade_value,
    }


# ---------------------------------------------------------------------------
# _parse_minute_key
# ---------------------------------------------------------------------------


def test_parse_minute_key_normal() -> None:
    assert _parse_minute_key("134501") == "1345"


def test_parse_minute_key_exact_four_chars() -> None:
    assert _parse_minute_key("0900") == "0900"


def test_parse_minute_key_too_short() -> None:
    assert _parse_minute_key("134") is None


def test_parse_minute_key_none() -> None:
    assert _parse_minute_key(None) is None


def test_parse_minute_key_empty_string() -> None:
    assert _parse_minute_key("") is None


def test_parse_minute_key_non_digit_prefix() -> None:
    assert _parse_minute_key("ABCD01") is None


# ---------------------------------------------------------------------------
# _recalculate_delta (독립 테스트)
# ---------------------------------------------------------------------------


def test_recalculate_delta_normal() -> None:
    b = MinuteBucket(minute_key="1345", base_code="000660", exchange="sor",
                     first_accumulated_trade_value=1_000, last_accumulated_trade_value=5_000)
    _recalculate_delta(b)
    assert b.minute_trade_value_delta == 4_000


def test_recalculate_delta_negative_is_none() -> None:
    b = MinuteBucket(minute_key="1345", base_code="000660", exchange="sor",
                     first_accumulated_trade_value=5_000, last_accumulated_trade_value=1_000)
    _recalculate_delta(b)
    assert b.minute_trade_value_delta is None


def test_recalculate_delta_first_none_is_none() -> None:
    b = MinuteBucket(minute_key="1345", base_code="000660", exchange="sor",
                     first_accumulated_trade_value=None, last_accumulated_trade_value=5_000)
    _recalculate_delta(b)
    assert b.minute_trade_value_delta is None


# ---------------------------------------------------------------------------
# 빈 ingest
# ---------------------------------------------------------------------------


def test_empty_ingest_no_state() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([])
    assert agg.get_latest_snapshot() == []
    assert agg.get_minute_buckets() == []


def test_row_without_base_code_ignored() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([{"base_code": None, "exchange": "sor"}])
    agg.ingest_rows([{"base_code": "", "exchange": "sor"}])
    assert agg.get_latest_snapshot() == []
    assert agg.get_minute_buckets() == []


# ---------------------------------------------------------------------------
# latest 상태 업데이트
# ---------------------------------------------------------------------------


def test_single_row_latest_state() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row()])
    states = agg.get_latest_snapshot()
    assert len(states) == 1
    s = states[0]
    assert s.base_code == "000660"
    assert s.exchange == "sor"
    assert s.latest_price == 70000
    assert s.latest_change_rate == 0.5
    assert s.latest_accumulated_volume == 1_000_000
    assert s.tick_count == 1


def test_latest_state_updates_on_second_tick() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(current_price=70000, trade_time="134501")])
    agg.ingest_rows([_row(current_price=71000, trade_time="134530")])
    s = agg.get_latest_snapshot()[0]
    assert s.latest_price == 71000
    assert s.last_trade_time == "134530"
    assert s.tick_count == 2


def test_different_exchange_separate_latest_state() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([
        _row(exchange="sor", current_price=70000),
        _row(exchange="nxt", current_price=70100),
    ])
    states = {s.exchange: s for s in agg.get_latest_snapshot()}
    assert len(states) == 2
    assert states["sor"].latest_price == 70000
    assert states["nxt"].latest_price == 70100


def test_multiple_codes_separate_latest_states() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([
        _row(base_code="000660", current_price=70000),
        _row(base_code="005930", current_price=55000),
    ])
    assert len(agg.get_latest_snapshot()) == 2


# ---------------------------------------------------------------------------
# 1분 bucket 생성
# ---------------------------------------------------------------------------


def test_single_row_creates_bucket() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", current_price=70000)])
    buckets = agg.get_minute_buckets()
    assert len(buckets) == 1
    b = buckets[0]
    assert b.minute_key == "1345"
    assert b.base_code == "000660"
    assert b.exchange == "sor"
    assert b.open_price == 70000
    assert b.high_price == 70000
    assert b.low_price == 70000
    assert b.close_price == 70000
    assert b.tick_count == 1
    assert b.first_trade_time == "134501"
    assert b.last_trade_time == "134501"


def test_ohlc_multiple_ticks_same_minute() -> None:
    agg = IntradayTickAggregator()
    prices = [70000, 71500, 69500, 71000]
    for i, p in enumerate(prices):
        agg.ingest_rows([_row(trade_time=f"13450{i}", current_price=p)])
    buckets = agg.get_minute_buckets()
    assert len(buckets) == 1
    b = buckets[0]
    assert b.open_price == 70000   # 첫 가격
    assert b.high_price == 71500   # 최고
    assert b.low_price == 69500    # 최저
    assert b.close_price == 71000  # 마지막 가격
    assert b.tick_count == 4


def test_different_minute_creates_separate_buckets() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([
        _row(trade_time="134501"),
        _row(trade_time="134601"),
    ])
    buckets = agg.get_minute_buckets()
    assert len(buckets) == 2
    assert {b.minute_key for b in buckets} == {"1345", "1346"}


def test_different_codes_same_minute_separate_buckets() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([
        _row(base_code="000660", trade_time="134501"),
        _row(base_code="005930", trade_time="134501"),
    ])
    assert len(agg.get_minute_buckets()) == 2
    assert len(agg.get_latest_snapshot()) == 2


def test_exchange_different_creates_separate_buckets() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([
        _row(exchange="sor", trade_time="134501"),
        _row(exchange="nxt", trade_time="134501"),
    ])
    assert len(agg.get_minute_buckets()) == 2


# ---------------------------------------------------------------------------
# trade_time 이상값 방어
# ---------------------------------------------------------------------------


def test_empty_trade_time_no_bucket_latest_updated() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="", current_price=70000)])
    assert agg.get_minute_buckets() == []
    s = agg.get_latest_snapshot()[0]
    assert s.latest_price == 70000
    assert s.tick_count == 1


def test_none_trade_time_no_bucket_latest_updated() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time=None, current_price=70000)])
    assert agg.get_minute_buckets() == []
    assert agg.get_latest_snapshot()[0].tick_count == 1


def test_short_trade_time_no_bucket() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134")])
    assert agg.get_minute_buckets() == []


def test_non_digit_trade_time_no_bucket() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="ABCD01")])
    assert agg.get_minute_buckets() == []


# ---------------------------------------------------------------------------
# 1분 거래대금 delta
# ---------------------------------------------------------------------------


def test_trade_value_delta_two_ticks() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", accumulated_trade_value=1_000_000)])
    agg.ingest_rows([_row(trade_time="134530", accumulated_trade_value=5_000_000)])
    b = agg.get_minute_buckets()[0]
    assert b.first_accumulated_trade_value == 1_000_000
    assert b.last_accumulated_trade_value == 5_000_000
    assert b.minute_trade_value_delta == 4_000_000


def test_trade_value_delta_single_tick_is_zero() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", accumulated_trade_value=3_000_000)])
    b = agg.get_minute_buckets()[0]
    assert b.minute_trade_value_delta == 0


def test_trade_value_none_yields_none_delta() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", accumulated_trade_value=None)])
    b = agg.get_minute_buckets()[0]
    assert b.first_accumulated_trade_value is None
    assert b.minute_trade_value_delta is None


def test_trade_value_negative_delta_is_none() -> None:
    """accumulated_trade_value 역전(음수 delta) → None으로 처리한다."""
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", accumulated_trade_value=5_000_000)])
    agg.ingest_rows([_row(trade_time="134530", accumulated_trade_value=1_000_000)])
    b = agg.get_minute_buckets()[0]
    assert b.minute_trade_value_delta is None


def test_trade_value_first_none_then_value() -> None:
    """첫 tick이 None이고 두 번째 tick이 값을 가지면 두 번째 값이 first로 설정된다.

    구현 정책: first_accumulated_trade_value는 "첫 번째 유효(non-None) 값"으로 설정한다.
    따라서 first == last == 5M → delta = 0.
    """
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(trade_time="134501", accumulated_trade_value=None)])
    agg.ingest_rows([_row(trade_time="134530", accumulated_trade_value=5_000_000)])
    b = agg.get_minute_buckets()[0]
    assert b.first_accumulated_trade_value == 5_000_000
    assert b.last_accumulated_trade_value == 5_000_000
    assert b.minute_trade_value_delta == 0


# ---------------------------------------------------------------------------
# get_top_by_minute_trade_value
# ---------------------------------------------------------------------------


def _build_agg(specs: list[tuple[str, int, int]]) -> IntradayTickAggregator:
    """(base_code, tv_start, tv_end) 리스트로 aggregator 준비 (같은 분, exchange=sor)."""
    agg = IntradayTickAggregator()
    for code, start, end in specs:
        agg.ingest_rows([_row(base_code=code, trade_time="134501", accumulated_trade_value=start)])
        agg.ingest_rows([_row(base_code=code, trade_time="134530", accumulated_trade_value=end)])
    return agg


def test_get_top_empty_aggregator() -> None:
    agg = IntradayTickAggregator()
    assert agg.get_top_by_minute_trade_value() == []


def test_get_top_sorted_by_delta_descending() -> None:
    specs = [
        ("000660", 100, 500),   # delta=400
        ("005930", 200, 600),   # delta=400 (same)
        ("035720", 50, 80),     # delta=30
        ("000080", 300, 800),   # delta=500
    ]
    agg = _build_agg(specs)
    top = agg.get_top_by_minute_trade_value(limit=10, minute_key="1345")
    deltas = [b.minute_trade_value_delta for b in top]
    assert deltas == sorted(deltas, reverse=True)
    assert top[0].minute_trade_value_delta == 500


def test_get_top_limit_applied() -> None:
    specs = [("00066" + str(i), i * 100, i * 200) for i in range(1, 6)]
    agg = _build_agg(specs)
    top = agg.get_top_by_minute_trade_value(limit=3, minute_key="1345")
    assert len(top) == 3


def test_get_top_latest_minute_auto_selected() -> None:
    """minute_key=None이면 가장 최신 minute_key(HHMM 최댓값) 자동 선택."""
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=100)])
    agg.ingest_rows([_row(base_code="000660", trade_time="134601", accumulated_trade_value=200)])
    agg.ingest_rows([_row(base_code="005930", trade_time="134601", accumulated_trade_value=300)])
    top = agg.get_top_by_minute_trade_value(limit=10)
    assert all(b.minute_key == "1346" for b in top)
    assert len(top) == 2


def test_get_top_none_delta_sorted_last() -> None:
    """delta가 None인 bucket은 후순위로 정렬된다."""
    agg = IntradayTickAggregator()
    # 005930: delta=400
    agg.ingest_rows([_row(base_code="005930", trade_time="134501", accumulated_trade_value=100)])
    agg.ingest_rows([_row(base_code="005930", trade_time="134530", accumulated_trade_value=500)])
    # 000660: accumulated_trade_value=None → delta=None
    agg.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=None)])
    top = agg.get_top_by_minute_trade_value(limit=10, minute_key="1345")
    assert len(top) == 2
    assert top[0].base_code == "005930"
    assert top[-1].minute_trade_value_delta is None


def test_get_top_specific_minute_key() -> None:
    agg = IntradayTickAggregator()
    agg.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=100)])
    agg.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=500)])
    agg.ingest_rows([_row(base_code="005930", trade_time="134601", accumulated_trade_value=200)])
    agg.ingest_rows([_row(base_code="005930", trade_time="134630", accumulated_trade_value=900)])
    top_1345 = agg.get_top_by_minute_trade_value(limit=10, minute_key="1345")
    top_1346 = agg.get_top_by_minute_trade_value(limit=10, minute_key="1346")
    assert all(b.minute_key == "1345" for b in top_1345)
    assert all(b.minute_key == "1346" for b in top_1346)
