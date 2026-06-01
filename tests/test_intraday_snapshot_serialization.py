"""src/intraday_snapshot_serialization.py 단위 테스트."""
from __future__ import annotations

import json
from datetime import datetime

from src.intraday_snapshot_service import IntradaySnapshotService
from src.intraday_snapshot_serialization import snapshot_to_dict


def _make_empty_snap():
    svc = IntradaySnapshotService({})
    return svc.get_snapshot()


def _make_ready_snap():
    sm = {"000660": ["반도체"], "005930": ["반도체"], "042660": ["조선"]}
    svc = IntradaySnapshotService(sm)
    # ingest some rows
    from src.intraday_snapshot_service import IntradaySnapshotService as S  # noqa: F401
    rows = [
        {"base_code": "000660", "exchange": "sor", "trade_time": "134501",
         "current_price": 70000, "change_rate": 1.5,
         "accumulated_trade_value": 5_000_000_000, "accumulated_volume": 100000},
        {"base_code": "000660", "exchange": "sor", "trade_time": "134530",
         "current_price": 70500, "change_rate": 1.8,
         "accumulated_trade_value": 6_000_000_000, "accumulated_volume": 110000},
        {"base_code": "005930", "exchange": "sor", "trade_time": "134501",
         "current_price": 81000, "change_rate": 0.5,
         "accumulated_trade_value": 8_000_000_000, "accumulated_volume": 200000},
        {"base_code": "042660", "exchange": "sor", "trade_time": "134501",
         "current_price": 25000, "change_rate": -0.3,
         "accumulated_trade_value": 1_000_000_000, "accumulated_volume": 50000},
    ]
    svc.ingest_rows(rows)
    return svc.get_snapshot()


# ---------------------------------------------------------------------------
# 1. 기본 구조
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_returns_dict():
    d = snapshot_to_dict(_make_empty_snap())
    assert isinstance(d, dict)


def test_snapshot_to_dict_is_json_serializable():
    d = snapshot_to_dict(_make_empty_snap())
    s = json.dumps(d)
    assert isinstance(s, str)


def test_snapshot_to_dict_required_keys():
    d = snapshot_to_dict(_make_empty_snap())
    required = [
        "generated_at", "minute_key", "status",
        "latest_count", "unmapped_count", "bucket_count",
        "raw_row_count", "ignored_row_count", "sector_count",
        "sector_views",
    ]
    for k in required:
        assert k in d, f"Missing key: {k}"


def test_snapshot_to_dict_no_credentials():
    d = snapshot_to_dict(_make_empty_snap())
    text = json.dumps(d).lower()
    for cred in ("token", "appkey", "secretkey"):
        assert cred not in text


# ---------------------------------------------------------------------------
# 2. empty snapshot
# ---------------------------------------------------------------------------


def test_empty_snapshot_status():
    d = snapshot_to_dict(_make_empty_snap())
    assert d["status"] == "empty"


def test_empty_snapshot_sector_views_is_list():
    d = snapshot_to_dict(_make_empty_snap())
    assert isinstance(d["sector_views"], list)
    assert d["sector_views"] == []


def test_empty_snapshot_generated_at_is_iso():
    d = snapshot_to_dict(_make_empty_snap())
    # should be parseable as ISO datetime
    dt = datetime.fromisoformat(d["generated_at"])
    assert isinstance(dt, datetime)


# ---------------------------------------------------------------------------
# 3. ready snapshot
# ---------------------------------------------------------------------------


def test_ready_snapshot_has_sector_views():
    d = snapshot_to_dict(_make_ready_snap())
    assert d["status"] in ("ready", "warming")
    assert isinstance(d["sector_views"], list)


def test_ready_snapshot_sector_view_keys():
    d = snapshot_to_dict(_make_ready_snap())
    if not d["sector_views"]:
        return  # sector might be warming
    sv = d["sector_views"][0]
    for k in ("rank", "sector_name", "sector_score", "total_minute_trade_value",
              "average_change_rate", "rising_ratio", "active_stock_count",
              "leader_stocks"):
        assert k in sv, f"Missing sector key: {k}"


def test_ready_snapshot_leader_stock_keys():
    d = snapshot_to_dict(_make_ready_snap())
    for sv in d["sector_views"]:
        for ls in sv["leader_stocks"]:
            for k in ("rank", "base_code", "exchange", "close_price",
                      "last_change_rate", "minute_trade_value_delta",
                      "display_badge"):
                assert k in ls, f"Missing leader key: {k}"


def test_ready_snapshot_is_fully_json_serializable():
    d = snapshot_to_dict(_make_ready_snap())
    s = json.dumps(d, ensure_ascii=False)
    restored = json.loads(s)
    assert restored["status"] == d["status"]
