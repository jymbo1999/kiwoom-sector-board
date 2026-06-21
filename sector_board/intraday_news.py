# sector_board/intraday_news.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

RISE_PCT = 0.08
FALL_PCT = -0.08
SECTOR_STOCK_PCT = 0.10
SECTOR_MIN_STOCKS = 3
STAGE_OFFSETS = {"T0": 0, "T+10": 10, "T+30": 30}

_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")
_TAG = re.compile(r"<[^>]+>")


def normalize_title(title: str | None) -> str:
    text = _TAG.sub("", str(title or ""))
    text = text.lower()
    text = _NON_WORD.sub("", text)
    return text


def article_dedupe_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        return f"url:{url}"
    basis = normalize_title(item.get("title")) + "|" + str(item.get("provider") or "") + "|" + str(item.get("published_at") or "")
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
    return f"h:{digest}"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_movers_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, list[dict]]:
    """런타임 스냅샷의 다양한 키를 관용적으로 읽어 정규화한다."""
    snapshot = snapshot or {}
    leaders_raw = snapshot.get("leaders") or snapshot.get("leader_stocks") or []
    sectors_raw = snapshot.get("sectors") or snapshot.get("sector_views") or []
    leaders = []
    for ls in leaders_raw:
        if not isinstance(ls, dict):
            continue
        leaders.append({
            "stock_code": str(ls.get("base_code") or ls.get("code") or ls.get("ticker") or ""),
            "stock_name": str(ls.get("name") or ls.get("stock_name") or ""),
            "sector_name": str(ls.get("sector_name") or ls.get("sector") or ls.get("theme_name") or ""),
            "change_rate": _f(ls.get("last_change_rate", ls.get("change_rate", ls.get("pct_change")))),
        })
    sectors = []
    for sv in sectors_raw:
        if not isinstance(sv, dict):
            continue
        sectors.append({
            "sector_name": str(sv.get("sector_name") or ""),
            "average_change_rate": _f(sv.get("average_change_rate", sv.get("avg_change_rate"))),
        })
    return {"leaders": leaders, "sectors": sectors}


def detect_intraday_news_events(
    snapshot: dict[str, Any] | None,
    *,
    top5_sectors: list[str] | None = None,
) -> list[dict[str, Any]]:
    movers = extract_movers_from_snapshot(snapshot)
    top5 = set(top5_sectors or [])
    candidates: list[dict[str, Any]] = []

    # 종목 이벤트
    for ls in movers["leaders"]:
        rate = ls["change_rate"]
        if not ls["stock_code"]:
            continue
        if rate >= RISE_PCT:
            etype = "rise"
        elif rate <= FALL_PCT:
            etype = "fall"
        else:
            continue
        candidates.append({
            "event_type": etype, "scope": "stock",
            "sector_name": ls["sector_name"] or None,
            "stock_code": ls["stock_code"], "stock_name": ls["stock_name"],
            "change_rate": rate, "short_change_rate": None,
            "trigger_reason": f"종목 일중 등락률 {rate*100:.1f}%",
        })

    # 섹터 이벤트: 같은 섹터 +10% 이상 종목 3개↑ 또는 Top5 신규 진입
    by_sector: dict[str, list[dict]] = {}
    for ls in movers["leaders"]:
        if ls["sector_name"]:
            by_sector.setdefault(ls["sector_name"], []).append(ls)
    for sv in movers["sectors"]:
        name = sv["sector_name"]
        if not name:
            continue
        strong = [s for s in by_sector.get(name, []) if s["change_rate"] >= SECTOR_STOCK_PCT]
        is_new_top5 = name in top5
        if len(strong) >= SECTOR_MIN_STOCKS or is_new_top5:
            reason = (
                f"섹터 내 +{SECTOR_STOCK_PCT*100:.0f}% 이상 종목 {len(strong)}개"
                if len(strong) >= SECTOR_MIN_STOCKS else "인트라데이 Top5 신규 진입"
            )
            candidates.append({
                "event_type": "rise", "scope": "sector",
                "sector_name": name, "stock_code": None, "stock_name": None,
                "change_rate": sv["average_change_rate"], "short_change_rate": None,
                "trigger_reason": reason,
            })
    return candidates
