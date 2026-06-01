"""장중 snapshot JSONL 읽기 유틸.

A안: logs/intraday_snapshot_*.jsonl 중 가장 최신 파일의
마지막 줄을 읽어 Flask template 렌더링용 view dict 를 반환한다.

Flask/DB 와 무관한 순수 함수 레이어이므로 단독 테스트가 가능하다.
"""
from __future__ import annotations

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# JSONL 로더
# ---------------------------------------------------------------------------


def find_latest_snapshot_jsonl(logs_dir: Path) -> Path | None:
    """logs_dir 에서 intraday_snapshot_*.jsonl 파일 중 가장 최신 파일을 반환한다.

    파일이 없으면 None 을 반환한다. 파일명 사전순 내림차순의 마지막 파일이 최신이다.
    """
    files = sorted(logs_dir.glob("intraday_snapshot_*.jsonl"))
    return files[-1] if files else None


def read_last_snapshot(path: Path) -> dict | None:
    """JSONL 파일에서 비어 있지 않은 마지막 줄을 읽어 dict 를 반환한다.

    파일이 없거나 JSON 파싱 실패 시 None 을 반환한다.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def load_latest_intraday_snapshot(logs_dir: Path) -> dict | None:
    """logs_dir 에서 가장 최신 intraday snapshot 을 로드한다.

    파일이 없거나 파싱 실패 시 None 을 반환한다.
    """
    path = find_latest_snapshot_jsonl(logs_dir)
    if path is None:
        return None
    return read_last_snapshot(path)


# ---------------------------------------------------------------------------
# 포맷 헬퍼 (template 렌더링용)
# ---------------------------------------------------------------------------


def _fmt_trade_value(v: int | float | None) -> str:
    """거래대금을 사람이 읽기 쉬운 문자열로 변환한다."""
    if v is None:
        return "N/A"
    v = int(v)
    if v >= 100_000_000_000:
        return f"{v / 100_000_000_000:.1f}천억"
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v // 10_000}만"
    return str(v)


def _fmt_rate(v: float | None) -> str:
    """등락률을 부호 포함 문자열로 변환한다."""
    if v is None:
        return "N/A"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_rising_ratio(v: float | None) -> str:
    """상승비율을 % 문자열로 변환한다."""
    if v is None:
        return "N/A"
    return f"{v * 100:.0f}%"


# ---------------------------------------------------------------------------
# View 빌더
# ---------------------------------------------------------------------------


def _build_leader_stock(ls: dict) -> dict:
    rate_val = ls.get("last_change_rate")
    return {
        "rank": ls.get("rank") or 0,
        "base_code": ls.get("base_code") or "",
        "exchange": ls.get("exchange") or "",
        "close_price": ls.get("close_price"),
        "close_price_fmt": f"{ls['close_price']:,}" if ls.get("close_price") is not None else "N/A",
        "last_change_rate_val": rate_val,
        "last_change_rate": _fmt_rate(rate_val),
        "is_positive": (rate_val or 0) > 0,
        "is_negative": (rate_val or 0) < 0,
        "minute_trade_value_delta": ls.get("minute_trade_value_delta"),
        "minute_trade_value_fmt": _fmt_trade_value(ls.get("minute_trade_value_delta")),
        "display_badge": ls.get("display_badge") or "",
    }


def _build_sector_view(sv: dict) -> dict:
    avg_rate = sv.get("average_change_rate")
    leaders = [_build_leader_stock(ls) for ls in (sv.get("leader_stocks") or [])]
    return {
        "rank": sv.get("rank") or 0,
        "sector_name": sv.get("sector_name") or "",
        "sector_score": sv.get("sector_score") or 0,
        "total_minute_trade_value": sv.get("total_minute_trade_value") or 0,
        "total_minute_trade_fmt": _fmt_trade_value(sv.get("total_minute_trade_value")),
        "average_change_rate_val": avg_rate,
        "average_change_rate": _fmt_rate(avg_rate),
        "is_positive": (avg_rate or 0) > 0,
        "is_negative": (avg_rate or 0) < 0,
        "rising_ratio": sv.get("rising_ratio"),
        "rising_ratio_fmt": _fmt_rising_ratio(sv.get("rising_ratio")),
        "active_stock_count": sv.get("active_stock_count") or 0,
        "leader_stocks": leaders,
    }


def build_intraday_view(snapshot: dict | None) -> dict:
    """snapshot dict 에서 Flask template 렌더링용 view dict 를 만든다.

    snapshot 이 None 이거나 비어 있으면 empty 상태의 view 를 반환한다.
    화면이 죽지 않도록 모든 키에 안전한 기본값을 보장한다.
    """
    if not snapshot:
        return {
            "status": "empty",
            "minute_key": None,
            "generated_at": None,
            "latest_count": 0,
            "unmapped_count": 0,
            "bucket_count": 0,
            "raw_row_count": 0,
            "ignored_row_count": 0,
            "sector_count": 0,
            "sector_views": [],
            "has_data": False,
            "snapshot_file": None,
        }

    sector_views = [_build_sector_view(sv) for sv in (snapshot.get("sector_views") or [])]
    return {
        "status": snapshot.get("status") or "empty",
        "minute_key": snapshot.get("minute_key"),
        "generated_at": snapshot.get("generated_at"),
        "latest_count": snapshot.get("latest_count") or 0,
        "unmapped_count": snapshot.get("unmapped_count") or 0,
        "bucket_count": snapshot.get("bucket_count") or 0,
        "raw_row_count": snapshot.get("raw_row_count") or 0,
        "ignored_row_count": snapshot.get("ignored_row_count") or 0,
        "sector_count": snapshot.get("sector_count") or 0,
        "sector_views": sector_views,
        "has_data": bool(sector_views),
        "snapshot_file": snapshot.get("_source_file"),
    }
