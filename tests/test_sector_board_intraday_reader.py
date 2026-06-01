"""sector_board/intraday_reader.py 단위 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sector_board.intraday_reader import (
    _fmt_rate,
    _fmt_rising_ratio,
    _fmt_trade_value,
    build_intraday_view,
    find_latest_snapshot_jsonl,
    load_latest_intraday_snapshot,
    read_last_snapshot,
)


# ---------------------------------------------------------------------------
# 테스트용 snapshot fixture
# ---------------------------------------------------------------------------


def _make_snapshot(**overrides) -> dict:
    base = {
        "generated_at": "2026-06-01T13:45:00",
        "minute_key": "1345",
        "status": "ready",
        "latest_count": 150,
        "unmapped_count": 0,
        "bucket_count": 150,
        "raw_row_count": 18420,
        "ignored_row_count": 3,
        "sector_count": 2,
        "sector_views": [
            {
                "rank": 1,
                "sector_name": "반도체",
                "sector_score": 32500000.0,
                "total_minute_trade_value": 5_000_000_000,
                "average_change_rate": 2.31,
                "rising_ratio": 0.85,
                "active_stock_count": 12,
                "leader_stocks": [
                    {
                        "rank": 1,
                        "base_code": "005930",
                        "exchange": "sor",
                        "close_price": 81200,
                        "last_change_rate": 1.82,
                        "minute_trade_value_delta": 8_840_000_000,
                        "display_badge": "대장",
                    },
                    {
                        "rank": 2,
                        "base_code": "000660",
                        "exchange": "sor",
                        "close_price": 182000,
                        "last_change_rate": 3.20,
                        "minute_trade_value_delta": 7_360_000_000,
                        "display_badge": "2등주",
                    },
                    {
                        "rank": 3,
                        "base_code": "042700",
                        "exchange": "sor",
                        "close_price": 32100,
                        "last_change_rate": -0.50,
                        "minute_trade_value_delta": 2_320_000_000,
                        "display_badge": "3등주",
                    },
                ],
            },
            {
                "rank": 2,
                "sector_name": "조선",
                "sector_score": 8500000.0,
                "total_minute_trade_value": 1_000_000_000,
                "average_change_rate": -0.30,
                "rising_ratio": 0.33,
                "active_stock_count": 3,
                "leader_stocks": [
                    {
                        "rank": 1,
                        "base_code": "042660",
                        "exchange": "sor",
                        "close_price": 25000,
                        "last_change_rate": -0.30,
                        "minute_trade_value_delta": 800_000_000,
                        "display_badge": "대장",
                    },
                ],
            },
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. _fmt_trade_value
# ---------------------------------------------------------------------------


def test_fmt_trade_value_thousand_eok() -> None:
    assert _fmt_trade_value(500_000_000_000) == "5.0천억"


def test_fmt_trade_value_eok() -> None:
    # 100_000_000(1억) 이상 100_000_000_000(1000억) 미만만 '억' 단위 출력
    assert _fmt_trade_value(5_000_000_000) == "50.0억"


def test_fmt_trade_value_small_eok() -> None:
    assert _fmt_trade_value(100_000_000) == "1.0억"


def test_fmt_trade_value_man() -> None:
    assert _fmt_trade_value(50_000) == "5만"


def test_fmt_trade_value_none() -> None:
    assert _fmt_trade_value(None) == "N/A"


def test_fmt_trade_value_zero() -> None:
    assert _fmt_trade_value(0) == "0"


# ---------------------------------------------------------------------------
# 2. _fmt_rate
# ---------------------------------------------------------------------------


def test_fmt_rate_positive() -> None:
    assert _fmt_rate(2.31) == "+2.31%"


def test_fmt_rate_negative() -> None:
    assert _fmt_rate(-1.50) == "-1.50%"


def test_fmt_rate_zero() -> None:
    assert _fmt_rate(0.0) == "0.00%"


def test_fmt_rate_none() -> None:
    assert _fmt_rate(None) == "N/A"


# ---------------------------------------------------------------------------
# 3. _fmt_rising_ratio
# ---------------------------------------------------------------------------


def test_fmt_rising_ratio_full() -> None:
    assert _fmt_rising_ratio(1.0) == "100%"


def test_fmt_rising_ratio_half() -> None:
    assert _fmt_rising_ratio(0.5) == "50%"


def test_fmt_rising_ratio_none() -> None:
    assert _fmt_rising_ratio(None) == "N/A"


# ---------------------------------------------------------------------------
# 4. find_latest_snapshot_jsonl
# ---------------------------------------------------------------------------


def test_find_latest_returns_most_recent(tmp_path: Path) -> None:
    (tmp_path / "intraday_snapshot_20260601_090000.jsonl").write_text("{}")
    (tmp_path / "intraday_snapshot_20260601_134500.jsonl").write_text("{}")
    (tmp_path / "intraday_snapshot_20260601_100000.jsonl").write_text("{}")
    result = find_latest_snapshot_jsonl(tmp_path)
    assert result is not None
    assert result.name == "intraday_snapshot_20260601_134500.jsonl"


def test_find_latest_returns_none_when_empty(tmp_path: Path) -> None:
    assert find_latest_snapshot_jsonl(tmp_path) is None


def test_find_latest_ignores_non_snapshot_files(tmp_path: Path) -> None:
    (tmp_path / "kiwoom_ws_raw_20260601.jsonl").write_text("{}")
    assert find_latest_snapshot_jsonl(tmp_path) is None


# ---------------------------------------------------------------------------
# 5. read_last_snapshot
# ---------------------------------------------------------------------------


def test_read_last_snapshot_returns_last_line(tmp_path: Path) -> None:
    f = tmp_path / "snap.jsonl"
    snap1 = {"status": "warming", "minute_key": "0900"}
    snap2 = {"status": "ready", "minute_key": "1345"}
    f.write_text(json.dumps(snap1) + "\n" + json.dumps(snap2) + "\n", encoding="utf-8")
    result = read_last_snapshot(f)
    assert result is not None
    assert result["status"] == "ready"
    assert result["minute_key"] == "1345"


def test_read_last_snapshot_single_line(tmp_path: Path) -> None:
    f = tmp_path / "snap.jsonl"
    snap = {"status": "ready"}
    f.write_text(json.dumps(snap) + "\n", encoding="utf-8")
    assert read_last_snapshot(f) == {"status": "ready"}


def test_read_last_snapshot_file_not_found(tmp_path: Path) -> None:
    assert read_last_snapshot(tmp_path / "nonexistent.jsonl") is None


def test_read_last_snapshot_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")
    assert read_last_snapshot(f) is None


def test_read_last_snapshot_blank_lines_only(tmp_path: Path) -> None:
    f = tmp_path / "blank.jsonl"
    f.write_text("\n\n\n", encoding="utf-8")
    assert read_last_snapshot(f) is None


def test_read_last_snapshot_bad_json_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "bad.jsonl"
    f.write_text("{not json}\n", encoding="utf-8")
    assert read_last_snapshot(f) is None


# ---------------------------------------------------------------------------
# 6. load_latest_intraday_snapshot
# ---------------------------------------------------------------------------


def test_load_latest_reads_newest_file(tmp_path: Path) -> None:
    snap_a = {"status": "warming", "minute_key": "0900"}
    snap_b = {"status": "ready", "minute_key": "1345"}
    (tmp_path / "intraday_snapshot_20260601_090000.jsonl").write_text(
        json.dumps(snap_a) + "\n", encoding="utf-8"
    )
    (tmp_path / "intraday_snapshot_20260601_134500.jsonl").write_text(
        json.dumps(snap_b) + "\n", encoding="utf-8"
    )
    result = load_latest_intraday_snapshot(tmp_path)
    assert result is not None
    assert result["status"] == "ready"


def test_load_latest_returns_none_when_no_files(tmp_path: Path) -> None:
    assert load_latest_intraday_snapshot(tmp_path) is None


def test_load_latest_returns_none_for_missing_dir() -> None:
    assert load_latest_intraday_snapshot(Path("/nonexistent/dir")) is None


# ---------------------------------------------------------------------------
# 7. build_intraday_view — None 입력 → empty
# ---------------------------------------------------------------------------


def test_build_view_none_returns_empty() -> None:
    view = build_intraday_view(None)
    assert view["status"] == "empty"
    assert view["has_data"] is False
    assert view["sector_views"] == []
    assert view["latest_count"] == 0


def test_build_view_none_has_all_keys() -> None:
    view = build_intraday_view(None)
    required = [
        "status", "minute_key", "generated_at",
        "latest_count", "unmapped_count", "bucket_count",
        "raw_row_count", "ignored_row_count",
        "sector_count", "sector_views", "has_data",
    ]
    for key in required:
        assert key in view, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 8. build_intraday_view — 정상 snapshot
# ---------------------------------------------------------------------------


def test_build_view_ready_status() -> None:
    view = build_intraday_view(_make_snapshot())
    assert view["status"] == "ready"
    assert view["has_data"] is True
    assert view["sector_count"] == 2


def test_build_view_sector_count() -> None:
    view = build_intraday_view(_make_snapshot())
    assert len(view["sector_views"]) == 2


def test_build_view_sector_name_preserved() -> None:
    view = build_intraday_view(_make_snapshot())
    assert view["sector_views"][0]["sector_name"] == "반도체"
    assert view["sector_views"][1]["sector_name"] == "조선"


def test_build_view_sector_trade_value_formatted() -> None:
    view = build_intraday_view(_make_snapshot())
    sv = view["sector_views"][0]
    assert sv["total_minute_trade_fmt"] != "N/A"
    assert "억" in sv["total_minute_trade_fmt"] or "천억" in sv["total_minute_trade_fmt"]


def test_build_view_sector_rate_formatted() -> None:
    view = build_intraday_view(_make_snapshot())
    sv = view["sector_views"][0]
    assert sv["average_change_rate"] == "+2.31%"
    assert sv["is_positive"] is True


def test_build_view_sector_negative_rate() -> None:
    view = build_intraday_view(_make_snapshot())
    sv = view["sector_views"][1]
    assert sv["is_negative"] is True
    assert sv["average_change_rate"].startswith("-")


def test_build_view_rising_ratio_formatted() -> None:
    view = build_intraday_view(_make_snapshot())
    assert view["sector_views"][0]["rising_ratio_fmt"] == "85%"


# ---------------------------------------------------------------------------
# 9. build_intraday_view — leader stocks
# ---------------------------------------------------------------------------


def test_build_view_leader_count() -> None:
    view = build_intraday_view(_make_snapshot())
    leaders = view["sector_views"][0]["leader_stocks"]
    assert len(leaders) == 3


def test_build_view_leader_badges() -> None:
    view = build_intraday_view(_make_snapshot())
    leaders = view["sector_views"][0]["leader_stocks"]
    assert leaders[0]["display_badge"] == "대장"
    assert leaders[1]["display_badge"] == "2등주"
    assert leaders[2]["display_badge"] == "3등주"


def test_build_view_leader_code() -> None:
    view = build_intraday_view(_make_snapshot())
    assert view["sector_views"][0]["leader_stocks"][0]["base_code"] == "005930"


def test_build_view_leader_rate_positive() -> None:
    view = build_intraday_view(_make_snapshot())
    ls = view["sector_views"][0]["leader_stocks"][0]
    assert ls["last_change_rate"] == "+1.82%"
    assert ls["is_positive"] is True


def test_build_view_leader_rate_negative() -> None:
    view = build_intraday_view(_make_snapshot())
    ls = view["sector_views"][0]["leader_stocks"][2]  # -0.50%
    assert ls["is_negative"] is True


def test_build_view_leader_price_formatted() -> None:
    view = build_intraday_view(_make_snapshot())
    ls = view["sector_views"][0]["leader_stocks"][0]
    assert ls["close_price_fmt"] == "81,200"


def test_build_view_leader_price_none_shows_na() -> None:
    snap = _make_snapshot()
    snap["sector_views"][0]["leader_stocks"][0]["close_price"] = None
    view = build_intraday_view(snap)
    assert view["sector_views"][0]["leader_stocks"][0]["close_price_fmt"] == "N/A"


def test_build_view_leader_tv_formatted() -> None:
    view = build_intraday_view(_make_snapshot())
    ls = view["sector_views"][0]["leader_stocks"][0]
    assert ls["minute_trade_value_fmt"] != "N/A"
    assert "억" in ls["minute_trade_value_fmt"] or "천억" in ls["minute_trade_value_fmt"]


# ---------------------------------------------------------------------------
# 10. build_intraday_view — 빈 sector_views → has_data=False
# ---------------------------------------------------------------------------


def test_build_view_empty_sector_views() -> None:
    snap = _make_snapshot(sector_views=[])
    view = build_intraday_view(snap)
    assert view["has_data"] is False
    assert view["sector_views"] == []


def test_build_view_warming_status() -> None:
    snap = _make_snapshot(status="warming", sector_views=[])
    view = build_intraday_view(snap)
    assert view["status"] == "warming"
    assert view["has_data"] is False


# ---------------------------------------------------------------------------
# 11. unmapped_count 표시
# ---------------------------------------------------------------------------


def test_build_view_unmapped_count_preserved() -> None:
    snap = _make_snapshot(unmapped_count=5)
    view = build_intraday_view(snap)
    assert view["unmapped_count"] == 5
