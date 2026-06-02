from __future__ import annotations

from datetime import datetime

import pandas as pd

from sector_board.payload import normalize_snapshot_payload
from src.intraday_snapshot_service import build_intraday_snapshot_payload


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"code": "100001", "name": "A1", "sector": "반도체", "theme": "A", "market": "KOSPI", "market_cap": 900},
            {"code": "100002", "name": "A2", "sector": "반도체", "theme": "A", "market": "KOSPI", "market_cap": 800},
            {"code": "200001", "name": "B1", "sector": "조선", "theme": "B", "market": "KOSPI", "market_cap": 700},
            {"code": "300001", "name": "C1", "sector": "바이오", "theme": "C", "market": "KOSDAQ", "market_cap": 600},
            {"code": "400001", "name": "D1", "sector": "로봇", "theme": "D", "market": "KOSDAQ", "market_cap": 500},
            {"code": "500001", "name": "E1", "sector": "자동차", "theme": "E", "market": "KOSPI", "market_cap": 400},
            {"code": "600001", "name": "F1", "sector": "게임", "theme": "F", "market": "KOSDAQ", "market_cap": 300},
        ]
    )


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"code": "100001", "name": "A1", "current_price": 110, "open_price": 100, "prev_close": 100, "change_rate": 10, "volume": 100, "trade_value": 100_000, "accumulated_trade_value": 100_000, "minute_trade_value": 10_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "100002", "name": "A2", "current_price": 106, "open_price": 100, "prev_close": 100, "change_rate": 6, "volume": 90, "trade_value": 90_000, "accumulated_trade_value": 90_000, "minute_trade_value": 9_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "200001", "name": "B1", "current_price": 105, "open_price": 100, "prev_close": 100, "change_rate": 5, "volume": 80, "trade_value": 80_000, "accumulated_trade_value": 80_000, "minute_trade_value": 8_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "300001", "name": "C1", "current_price": 104, "open_price": 100, "prev_close": 100, "change_rate": 4, "volume": 70, "trade_value": 70_000, "accumulated_trade_value": 70_000, "minute_trade_value": 7_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "400001", "name": "D1", "current_price": 103, "open_price": 100, "prev_close": 100, "change_rate": 3, "volume": 60, "trade_value": 60_000, "accumulated_trade_value": 60_000, "minute_trade_value": 6_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "500001", "name": "E1", "current_price": 102, "open_price": 100, "prev_close": 100, "change_rate": 2, "volume": 50, "trade_value": 50_000, "accumulated_trade_value": 50_000, "minute_trade_value": 5_000, "updated_at": "2026-06-01T09:30:00"},
            {"code": "600001", "name": "F1", "current_price": 101, "open_price": 100, "prev_close": 100, "change_rate": 1, "volume": 40, "trade_value": 40_000, "accumulated_trade_value": 40_000, "minute_trade_value": 4_000, "updated_at": "2026-06-01T09:30:00"},
        ]
    )


def test_build_intraday_snapshot_payload_is_repository_compatible() -> None:
    payload = build_intraday_snapshot_payload(
        _quotes(),
        _universe(),
        data_mode="mock",
        provider_mode="mock",
        generated_at=datetime(2026, 6, 1, 9, 30, 5),
        universe_metadata={"total_count": 7, "selected_count": 7},
    )

    assert payload["summary"]["board_type"] == "intraday"
    assert payload["summary"]["data_mode"] == "mock"
    assert payload["summary"]["provider_mode"] == "mock"
    assert payload["summary"]["freshness_seconds"] == 5
    assert payload["summary"]["selected_sector_count"] == 5
    assert len(payload["themes"]) == 5
    assert len(payload["leaders"]) <= 7
    assert "rank_events" in payload
    assert "provider_status" in payload
    assert payload["provider_status"]["provider_mode"] == "mock"

    normalized = normalize_snapshot_payload(payload)

    assert normalized["summary"]["board_type"] == "intraday"
    assert len(normalized["themes"]) == 5
    assert normalized["leaders"]


def test_intraday_snapshot_theme_and_leader_keys_match_morning_template_shape() -> None:
    payload = build_intraday_snapshot_payload(_quotes(), _universe(), generated_at=datetime(2026, 6, 1, 9, 30, 0))
    theme = payload["themes"][0]
    leader = payload["leaders"][0]

    assert {"theme_id", "theme_name", "theme_score", "total_trading_value", "top5_change_rate_mean", "leader_labels"}.issubset(theme)
    assert {"rank", "theme_id", "theme_name", "code", "name", "change_rate", "trade_value", "leader_score"}.issubset(leader)


# ===========================================================================
# IntradaySnapshotService — v2 WebSocket 기반 집계 서비스 테스트
# ===========================================================================

import json
from typing import Any
from unittest.mock import patch

from src.intraday_snapshot_service import IntradaySnapshot, IntradaySnapshotService

SECTOR_MAP_V2: dict[str, list[str]] = {
    "000660": ["반도체"],
    "005930": ["반도체"],
    "042660": ["조선"],
}


def _row(
    base_code: str = "000660",
    exchange: str = "sor",
    trade_time: str | None = "134501",
    current_price: int | None = 70000,
    change_rate: float | None = 0.5,
    accumulated_trade_value: int | None = 1_000_000,
) -> dict[str, Any]:
    return {
        "base_code": base_code,
        "exchange": exchange,
        "trade_time": trade_time,
        "current_price": current_price,
        "change_rate": change_rate,
        "accumulated_volume": 100_000,
        "accumulated_trade_value": accumulated_trade_value,
    }


def _real_json(
    item: str = "000660_AL",
    price: str = "+70000",
    time: str = "134501",
    acc_tv: str = "+1000000",
) -> str:
    return json.dumps({
        "trnm": "REAL",
        "data": [{
            "item": item, "type": "0B", "name": "주식체결",
            "10": price, "20": time, "15": "+100", "13": "+100000", "14": acc_tv,
        }],
    })


def _real_json_values(
    item: str = "000660_AL",
    price: str = "+70000",
    time: str = "090501",
    acc_tv: str = "+1000000",
) -> str:
    return json.dumps({
        "trnm": "REAL",
        "data": [{
            "item": item,
            "type": "0B",
            "name": "주식체결",
            "values": {
                "10": price,
                "20": time,
                "15": "+100",
                "13": "+100000",
                "14": acc_tv,
                "12": "+0.50",
            },
        }],
    })


def _svc(**kwargs) -> IntradaySnapshotService:
    return IntradaySnapshotService(sector_map=SECTOR_MAP_V2, **kwargs)


# ---------------------------------------------------------------------------
# 1. 초기 snapshot은 empty
# ---------------------------------------------------------------------------


def test_v2_initial_snapshot_is_empty() -> None:
    snap = _svc().get_snapshot()
    assert snap.status == "empty"
    assert snap.sector_views == []
    assert snap.latest_count == 0
    assert snap.bucket_count == 0
    assert snap.minute_key is None


# ---------------------------------------------------------------------------
# 2. ingest_rows로 단일 normalized row 반영
# ---------------------------------------------------------------------------


def test_v2_ingest_single_row_updates_latest() -> None:
    svc = _svc()
    n = svc.ingest_rows([_row()])
    assert n == 1
    assert svc.get_snapshot().latest_count == 1


# ---------------------------------------------------------------------------
# 3. ingest_raw_message로 raw REAL JSON 반영
# ---------------------------------------------------------------------------


def test_v2_ingest_raw_message_real_json() -> None:
    svc = _svc()
    n = svc.ingest_raw_message(_real_json())
    assert n == 1
    snap = svc.get_snapshot()
    assert snap.latest_count == 1
    assert snap.bucket_count == 1


def test_v2_ingest_raw_message_nested_values_creates_minute_bucket() -> None:
    svc = _svc()

    n = svc.ingest_raw_message(_real_json_values())

    assert n == 1
    snap = svc.get_snapshot()
    assert snap.status == "ready"
    assert snap.latest_count == 1
    assert snap.bucket_count == 1
    assert snap.sector_count == 1
    assert snap.minute_key == "0905"


# ---------------------------------------------------------------------------
# 4. 여러 tick이 1분 bucket으로 묶이는지
# ---------------------------------------------------------------------------


def test_v2_multiple_ticks_same_minute_single_bucket() -> None:
    svc = _svc()
    for t in ["134501", "134515", "134530", "134545"]:
        svc.ingest_rows([_row(trade_time=t, accumulated_trade_value=int(t) * 1000)])
    snap = svc.get_snapshot()
    assert snap.bucket_count == 1
    assert snap.minute_key == "1345"


def test_v2_ticks_across_two_minutes_two_buckets() -> None:
    svc = _svc()
    svc.ingest_rows([_row(trade_time="134501")])
    svc.ingest_rows([_row(trade_time="134601")])
    assert svc.get_snapshot().bucket_count == 2


# ---------------------------------------------------------------------------
# 5. sector_map을 통해 sector_views 생성
# ---------------------------------------------------------------------------


def test_v2_sector_views_generated() -> None:
    svc = _svc()
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=5_000_000)])
    snap = svc.get_snapshot()
    assert snap.status == "ready"
    assert snap.sector_count >= 1
    assert snap.sector_views[0].sector_name == "반도체"


# ---------------------------------------------------------------------------
# 6. sector_limit 적용
# ---------------------------------------------------------------------------


def test_v2_sector_limit_applied() -> None:
    big_map = {f"00066{i}": [f"섹터{i}"] for i in range(5)}
    svc = IntradaySnapshotService(sector_map=big_map, sector_limit=2)
    for i in range(5):
        c = f"00066{i}"
        svc.ingest_rows([_row(base_code=c, trade_time="134501", accumulated_trade_value=100_000 * (5 - i))])
        svc.ingest_rows([_row(base_code=c, trade_time="134530", accumulated_trade_value=200_000 * (5 - i))])
    assert svc.get_snapshot().sector_count == 2


# ---------------------------------------------------------------------------
# 7. stock_limit 적용
# ---------------------------------------------------------------------------


def test_v2_stock_limit_applied() -> None:
    codes = [f"00066{i}" for i in range(5)]
    big_map = {c: ["반도체"] for c in codes}
    svc = IntradaySnapshotService(sector_map=big_map, stock_limit=2)
    for c in codes:
        svc.ingest_rows([_row(base_code=c, trade_time="134501", accumulated_trade_value=1_000_000)])
        svc.ingest_rows([_row(base_code=c, trade_time="134530", accumulated_trade_value=3_000_000)])
    snap = svc.get_snapshot()
    assert len(snap.sector_views[0].leader_stocks) == 2


# ---------------------------------------------------------------------------
# 8. min_total_trade_value 필터
# ---------------------------------------------------------------------------


def test_v2_min_total_trade_value_filter() -> None:
    svc = IntradaySnapshotService(sector_map=SECTOR_MAP_V2, min_total_trade_value=999_999_999)
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=100)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=200)])
    snap = svc.get_snapshot()
    assert snap.sector_count == 0
    assert snap.status == "warming"


# ---------------------------------------------------------------------------
# 9. min_active_stock_count 필터
# ---------------------------------------------------------------------------


def test_v2_min_active_stock_count_filter() -> None:
    svc = IntradaySnapshotService(sector_map=SECTOR_MAP_V2, min_active_stock_count=10)
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=5_000_000)])
    snap = svc.get_snapshot()
    assert snap.sector_count == 0
    assert snap.status == "warming"


# ---------------------------------------------------------------------------
# 10. unmapped 종목만 있으면 warming
# ---------------------------------------------------------------------------


def test_v2_unmapped_stocks_yield_warming() -> None:
    svc = IntradaySnapshotService(sector_map={"000660": ["반도체"]})
    svc.ingest_rows([_row(base_code="999999", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="999999", trade_time="134530", accumulated_trade_value=5_000_000)])
    snap = svc.get_snapshot()
    assert snap.bucket_count > 0
    assert snap.status == "warming"


# ---------------------------------------------------------------------------
# 11. trade_time 이상 → latest는 생기지만 bucket 없어 empty
# ---------------------------------------------------------------------------


def test_v2_invalid_trade_time_no_bucket_status_empty() -> None:
    svc = _svc()
    svc.ingest_rows([_row(trade_time="", current_price=70000)])
    snap = svc.get_snapshot()
    assert snap.latest_count == 1
    assert snap.bucket_count == 0
    assert snap.status == "empty"


def test_v2_none_trade_time_no_bucket() -> None:
    svc = _svc()
    svc.ingest_rows([_row(trade_time=None)])
    assert svc.get_snapshot().bucket_count == 0


# ---------------------------------------------------------------------------
# 12. normalize 실패 → 0 반환, ignored_row_count 증가
# ---------------------------------------------------------------------------


def test_v2_invalid_json_returns_zero_increments_ignored() -> None:
    svc = _svc()
    result = svc.ingest_raw_message("이것은 JSON이 아닙니다")
    assert result == 0
    assert svc.ignored_row_count == 1
    assert svc.raw_row_count == 0


def test_v2_non_real_message_returns_zero() -> None:
    svc = _svc()
    result = svc.ingest_raw_message(json.dumps({"trnm": "LOGIN", "return_code": 0}))
    assert result == 0
    assert svc.ignored_row_count == 1


# ---------------------------------------------------------------------------
# 13. 빈 rows ingest → 0 반환, ignored_row_count 증가
# ---------------------------------------------------------------------------


def test_v2_empty_rows_returns_zero_increments_ignored() -> None:
    svc = _svc()
    assert svc.ingest_rows([]) == 0
    assert svc.ignored_row_count == 1
    assert svc.raw_row_count == 0


# ---------------------------------------------------------------------------
# 14. base_code 없는 row는 무시
# ---------------------------------------------------------------------------


def test_v2_row_without_base_code_is_ignored() -> None:
    svc = _svc()
    result = svc.ingest_rows([{"exchange": "sor", "trade_time": "134501"}])
    assert result == 0
    assert svc.ignored_row_count == 1


# ---------------------------------------------------------------------------
# 15. exchange 없는 row는 무시
# ---------------------------------------------------------------------------


def test_v2_row_without_exchange_is_ignored() -> None:
    svc = _svc()
    result = svc.ingest_rows([{"base_code": "000660", "trade_time": "134501"}])
    assert result == 0
    assert svc.ignored_row_count == 1


# ---------------------------------------------------------------------------
# 16. get_snapshot(minute_key) 특정 분만 반환
# ---------------------------------------------------------------------------


def test_v2_specific_minute_key_filter() -> None:
    svc = _svc()
    svc.ingest_rows([_row(base_code="000660", trade_time="090101", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="090130", accumulated_trade_value=5_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=6_000_000)])
    snap = svc.get_snapshot(minute_key="0901")
    assert snap.minute_key == "0901"


# ---------------------------------------------------------------------------
# 17. minute_key=None이면 최신 분 기준
# ---------------------------------------------------------------------------


def test_v2_none_minute_key_uses_latest_minute() -> None:
    svc = _svc()
    svc.ingest_rows([_row(base_code="000660", trade_time="090101", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=5_000_000)])
    snap = svc.get_snapshot()
    assert snap.minute_key == "1345"


# ---------------------------------------------------------------------------
# 18. reset 후 상태 초기화
# ---------------------------------------------------------------------------


def test_v2_reset_clears_state() -> None:
    svc = _svc()
    svc.ingest_rows([_row(trade_time="134501")])
    svc.reset()
    assert svc.raw_row_count == 0
    assert svc.ignored_row_count == 0
    snap = svc.get_snapshot()
    assert snap.status == "empty"
    assert snap.latest_count == 0


# ---------------------------------------------------------------------------
# 19. raw_row_count 누적
# ---------------------------------------------------------------------------


def test_v2_raw_row_count_accumulates() -> None:
    svc = _svc()
    svc.ingest_rows([_row(trade_time="134501")])
    svc.ingest_rows([_row(trade_time="134502"), _row(base_code="005930", trade_time="134502")])
    assert svc.raw_row_count == 3


# ---------------------------------------------------------------------------
# 20. ignored_row_count 누적
# ---------------------------------------------------------------------------


def test_v2_ignored_row_count_accumulates() -> None:
    svc = _svc()
    svc.ingest_rows([])                                          # +1
    svc.ingest_raw_message("not json")                           # +1
    svc.ingest_rows([{"exchange": "sor"}])                       # base_code 없음 → +1
    assert svc.ignored_row_count == 3


# ---------------------------------------------------------------------------
# 21. generated_at이 datetime인지
# ---------------------------------------------------------------------------


def test_v2_generated_at_is_datetime() -> None:
    assert isinstance(_svc().get_snapshot().generated_at, datetime)


# ---------------------------------------------------------------------------
# 22. latest_count, bucket_count, sector_count 정확성
# ---------------------------------------------------------------------------


def test_v2_snapshot_counts_accurate() -> None:
    svc = IntradaySnapshotService(sector_map={"000660": ["반도체"], "042660": ["조선"]})
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=5_000_000)])
    svc.ingest_rows([_row(base_code="042660", trade_time="134501", accumulated_trade_value=500_000)])
    svc.ingest_rows([_row(base_code="042660", trade_time="134530", accumulated_trade_value=2_000_000)])
    snap = svc.get_snapshot()
    assert snap.latest_count == 2
    assert snap.bucket_count == 2
    assert snap.sector_count == 2


# ---------------------------------------------------------------------------
# 23. status 각각 검증
# ---------------------------------------------------------------------------


def test_v2_status_empty() -> None:
    assert _svc().get_snapshot().status == "empty"


def test_v2_status_warming() -> None:
    svc = IntradaySnapshotService(sector_map={"000660": ["반도체"]})
    svc.ingest_rows([_row(base_code="999999", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="999999", trade_time="134530", accumulated_trade_value=5_000_000)])
    assert svc.get_snapshot().status == "warming"


def test_v2_status_ready() -> None:
    svc = _svc()
    svc.ingest_rows([_row(base_code="000660", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="000660", trade_time="134530", accumulated_trade_value=5_000_000)])
    assert svc.get_snapshot().status == "ready"


# ---------------------------------------------------------------------------
# 24. 같은 종목이 여러 섹터에 속하면 양쪽 반영
# ---------------------------------------------------------------------------


def test_v2_stock_in_multiple_sectors() -> None:
    svc = IntradaySnapshotService(sector_map={"005930": ["반도체", "대형주"]})
    svc.ingest_rows([_row(base_code="005930", trade_time="134501", accumulated_trade_value=1_000_000)])
    svc.ingest_rows([_row(base_code="005930", trade_time="134530", accumulated_trade_value=5_000_000)])
    snap = svc.get_snapshot()
    assert snap.sector_count == 2
    names = {v.sector_name for v in snap.sector_views}
    assert names == {"반도체", "대형주"}


# ---------------------------------------------------------------------------
# 25. 서비스가 예외를 삼키고 죽지 않는지
# ---------------------------------------------------------------------------


def test_v2_service_survives_normalize_exception() -> None:
    svc = _svc()
    with patch(
        "src.intraday_snapshot_service._normalize_tick_rows",
        side_effect=RuntimeError("boom"),
    ):
        result = svc.ingest_raw_message('{"trnm": "REAL"}')
    assert result == 0
    assert svc.ignored_row_count == 1
    # 서비스가 살아있고 이후 정상 ingest 가능
    svc.ingest_rows([_row(trade_time="134501")])
    assert svc.raw_row_count == 1
