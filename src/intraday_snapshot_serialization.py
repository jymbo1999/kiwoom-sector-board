"""IntradaySnapshot → JSON 직렬화 가능 dict 변환 유틸.

scripts/run_intraday_snapshot_smoke.py 와 src/intraday_runtime.py 가
공통으로 사용한다. credential 필드(token, appkey, secretkey)는 포함하지 않는다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .intraday_snapshot_service import IntradaySnapshot


def snapshot_to_dict(snap: "IntradaySnapshot") -> dict:
    """IntradaySnapshot 을 JSON 직렬화 가능한 dict 로 변환한다.

    credential 필드를 포함하지 않으므로 JSONL 저장, HTTP API 응답 모두에 안전하다.
    """
    return {
        "generated_at": snap.generated_at.isoformat(),
        "minute_key": snap.minute_key,
        "status": snap.status,
        "latest_count": snap.latest_count,
        "unmapped_count": snap.unmapped_count,
        "bucket_count": snap.bucket_count,
        "raw_row_count": snap.raw_row_count,
        "ignored_row_count": snap.ignored_row_count,
        "sector_count": snap.sector_count,
        "sector_views": [
            {
                "rank": sv.rank,
                "sector_name": sv.sector_name,
                "sector_score": sv.sector_score,
                "total_minute_trade_value": sv.total_minute_trade_value,
                "average_change_rate": sv.average_change_rate,
                "rising_ratio": sv.rising_ratio,
                "active_stock_count": sv.active_stock_count,
                "leader_stocks": [
                    {
                        "rank": ls.rank,
                        "base_code": ls.base_code,
                        "exchange": ls.exchange,
                        "close_price": ls.close_price,
                        "last_change_rate": ls.last_change_rate,
                        "minute_trade_value_delta": ls.minute_trade_value_delta,
                        "display_badge": ls.display_badge,
                    }
                    for ls in sv.leader_stocks
                ],
            }
            for sv in snap.sector_views
        ],
    }
