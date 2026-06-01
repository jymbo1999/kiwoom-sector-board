"""장중 실시간 tick 집계 모듈.

normalize_tick_rows()가 반환하는 row dict 리스트를 받아
종목별 최신 상태(LatestTickState)와 1분 OHLC bucket(MinuteBucket)을 유지한다.

DB 저장, Flask UI, sector ranking과 무관한 순수 메모리 집계 레이어.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LatestTickState:
    """종목별 최신 tick 상태.

    key: (base_code, exchange)
    """

    base_code: str
    exchange: str
    latest_price: int | None = None
    latest_change_rate: float | None = None
    latest_accumulated_volume: int | None = None
    latest_accumulated_trade_value: int | None = None
    last_trade_time: str | None = None
    tick_count: int = 0


@dataclass
class MinuteBucket:
    """종목/분 단위 OHLC + 1분 거래대금 delta 집계.

    key: (minute_key, base_code, exchange)
    minute_trade_value_delta 정책:
      - accumulated_trade_value가 None이면 None
      - last < first (역전)이면 None (데이터 이상 또는 세션 리셋으로 간주)
    """

    minute_key: str            # HHMM (trade_time의 앞 4자)
    base_code: str
    exchange: str
    open_price: int | None = None
    high_price: int | None = None
    low_price: int | None = None
    close_price: int | None = None
    first_accumulated_trade_value: int | None = None
    last_accumulated_trade_value: int | None = None
    minute_trade_value_delta: int | None = None
    tick_count: int = 0
    last_change_rate: float | None = None
    first_trade_time: str | None = None
    last_trade_time: str | None = None


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _parse_minute_key(trade_time: str | None) -> str | None:
    """HHMMSS에서 HHMM(앞 4자)을 추출한다.

    길이 4 미만이거나 앞 4자가 비숫자이면 None을 반환한다.
    None 반환 시 호출자가 bucket 집계를 건너뛴다.
    """
    if not trade_time or len(trade_time) < 4:
        return None
    prefix = trade_time[:4]
    return prefix if prefix.isdigit() else None


def _recalculate_delta(bucket: MinuteBucket) -> None:
    """1분 거래대금 delta를 재계산한다.

    정책: delta < 0 (accumulated_trade_value 역전)이면 None으로 처리한다.
    역전 원인은 데이터 이상 또는 세션 리셋으로 가정하고 보수적으로 제외한다.
    """
    first = bucket.first_accumulated_trade_value
    last = bucket.last_accumulated_trade_value
    if first is None or last is None:
        bucket.minute_trade_value_delta = None
        return
    delta = last - first
    bucket.minute_trade_value_delta = delta if delta >= 0 else None


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class IntradayTickAggregator:
    """실시간 tick rows를 종목별 최신 상태 + 1분 OHLC bucket으로 집계한다.

    사용 예::

        aggregator = IntradayTickAggregator()
        aggregator.ingest_rows(normalize_tick_rows(raw_json))

        latest = aggregator.get_latest_snapshot()
        buckets = aggregator.get_minute_buckets()
        top = aggregator.get_top_by_minute_trade_value(limit=20)

    latest key : (base_code, exchange)
    bucket key : (minute_key, base_code, exchange)
    """

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str], LatestTickState] = {}
        self._buckets: dict[tuple[str, str, str], MinuteBucket] = {}

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_rows(self, rows: list[dict[str, Any]]) -> None:
        """normalize_tick_rows()의 결과를 일괄 처리한다."""
        for row in rows:
            self._ingest_one(row)

    def _ingest_one(self, row: dict[str, Any]) -> None:
        base_code: str = row.get("base_code") or ""
        if not base_code:
            return
        exchange: str = row.get("exchange") or "krx"

        price: int | None = row.get("current_price")
        change_rate: float | None = row.get("change_rate")
        acc_vol: int | None = row.get("accumulated_volume")
        acc_tv: int | None = row.get("accumulated_trade_value")
        trade_time: str | None = row.get("trade_time") or None

        # --- 최신 상태 업데이트 ---
        lkey = (base_code, exchange)
        if lkey not in self._latest:
            self._latest[lkey] = LatestTickState(base_code=base_code, exchange=exchange)
        state = self._latest[lkey]

        if price is not None:
            state.latest_price = price
        if change_rate is not None:
            state.latest_change_rate = change_rate
        if acc_vol is not None:
            state.latest_accumulated_volume = acc_vol
        if acc_tv is not None:
            state.latest_accumulated_trade_value = acc_tv
        if trade_time:
            state.last_trade_time = trade_time
        state.tick_count += 1

        # --- 1분 bucket 업데이트 ---
        minute_key = _parse_minute_key(trade_time)
        if minute_key is None:
            # 이상 trade_time → latest만 업데이트, bucket은 건너뜀
            return

        bkey = (minute_key, base_code, exchange)
        if bkey not in self._buckets:
            self._buckets[bkey] = MinuteBucket(
                minute_key=minute_key,
                base_code=base_code,
                exchange=exchange,
            )
        bucket = self._buckets[bkey]

        if price is not None:
            if bucket.open_price is None:
                bucket.open_price = price
            if bucket.high_price is None or price > bucket.high_price:
                bucket.high_price = price
            if bucket.low_price is None or price < bucket.low_price:
                bucket.low_price = price
            bucket.close_price = price

        if acc_tv is not None:
            if bucket.first_accumulated_trade_value is None:
                bucket.first_accumulated_trade_value = acc_tv
            bucket.last_accumulated_trade_value = acc_tv
            _recalculate_delta(bucket)

        if trade_time:
            if bucket.first_trade_time is None:
                bucket.first_trade_time = trade_time
            bucket.last_trade_time = trade_time

        if change_rate is not None:
            bucket.last_change_rate = change_rate

        bucket.tick_count += 1

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_latest_snapshot(self) -> list[LatestTickState]:
        """모든 종목의 최신 tick 상태를 반환한다."""
        return list(self._latest.values())

    def get_minute_buckets(self) -> list[MinuteBucket]:
        """모든 1분 bucket을 반환한다."""
        return list(self._buckets.values())

    def get_top_by_minute_trade_value(
        self,
        limit: int = 20,
        minute_key: str | None = None,
    ) -> list[MinuteBucket]:
        """1분 거래대금 delta 기준 상위 종목을 반환한다.

        minute_key=None이면 가장 최근 minute_key를 자동으로 선택한다.
        delta가 None인 bucket은 후순위로 정렬한다.
        """
        if not self._buckets:
            return []

        target = minute_key if minute_key is not None else max(k[0] for k in self._buckets)

        candidates = [b for b in self._buckets.values() if b.minute_key == target]
        candidates.sort(
            key=lambda b: (
                b.minute_trade_value_delta is None,
                -(b.minute_trade_value_delta or 0),
            )
        )
        return candidates[:limit]
