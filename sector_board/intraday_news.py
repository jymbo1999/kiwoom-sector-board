# sector_board/intraday_news.py
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
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


from . import news_repository as _nr
from .news_schema import news_events as _events_tbl  # noqa: F401  (참조 명시용)

try:
    from src.news_service import build_news_queries_for_mover, search_naver_news
except Exception:  # noqa: BLE001  (src 미가용 환경 대비)
    build_news_queries_for_mover = None
    search_naver_news = None


def _queries_for_event(event: dict[str, Any]) -> list[str]:
    if event.get("scope") == "sector":
        name = event.get("sector_name") or ""
        return [f"{name} 섹터 급등 이유", f"{name} 테마 강세"] if name else []
    if build_news_queries_for_mover is not None:
        return build_news_queries_for_mover({"name": event.get("stock_name"), "ticker": event.get("stock_code")})[:3]
    name = event.get("stock_name") or ""
    return [f"{name} 주가 상승 이유", f"{name} 급등 이유"] if name else []


def collect_news_for_event(
    engine,
    event: dict[str, Any],
    stage: str,
    *,
    now: datetime,
    search_fn: Callable[..., list[dict]] | None = None,
) -> int:
    """이벤트 1건에 대해 뉴스 수집 → 기사 영속(dedupe). 추가된 기사 수 반환. 실패해도 예외 안 냄."""
    search = search_fn or search_naver_news
    if search is None:
        return 0
    event_id = int(event["id"])
    added = 0
    try:
        _nr.set_event_status(engine, event_id, "collecting", now=now)
        for query in _queries_for_event(event):
            try:
                items = search(query, display=20, stock_name=event.get("stock_name"))
            except Exception:  # noqa: BLE001
                continue
            for item in items or []:
                article = {
                    "title": item.get("title"), "url": item.get("url"),
                    "provider": item.get("provider"), "published_at": item.get("published_at"),
                    "excerpt": item.get("excerpt"), "query": query, "stage": stage,
                    "dedupe_key": article_dedupe_key(item),
                }
                if _nr.insert_article(engine, event_id, article, now=now):
                    added += 1
        _nr.mark_stage_done(engine, event_id, stage, now=now)
        _nr.set_event_status(engine, event_id, "collected", now=now)
    except Exception:  # noqa: BLE001
        try:
            _nr.set_event_status(engine, event_id, "failed", now=now)
        except Exception:  # noqa: BLE001
            pass
    return added


def process_snapshot_once(
    engine,
    snapshot: dict[str, Any] | None,
    *,
    trade_date: date,
    now: datetime,
    top5_sectors: list[str] | None = None,
    search_fn: Callable[..., list[dict]] | None = None,
) -> None:
    """스냅샷 1장 처리: 감지 → 이벤트 upsert → T0 수집 + 도래한 T+10/T+30 보강. 예외 삼킴."""
    try:
        candidates = detect_intraday_news_events(snapshot, top5_sectors=top5_sectors)
    except Exception:  # noqa: BLE001
        candidates = []
    for cand in candidates:
        try:
            event_id = _nr.upsert_event(engine, cand, trade_date=trade_date, now=now)
            event = {"id": event_id, **cand}
            payload_done = _event_done_stages(engine, event_id)
            if "T0" not in payload_done:
                collect_news_for_event(engine, event, "T0", now=now, search_fn=search_fn)
        except Exception:  # noqa: BLE001
            continue
    _process_due_stages(engine, trade_date=trade_date, now=now, search_fn=search_fn)


def _event_done_stages(engine, event_id: int) -> set[str]:
    for ev in _nr.list_events_for_date_any(engine, event_id):
        return set(ev.get("payload", {}).get("done_stages", []))
    return set()


def _process_due_stages(engine, *, trade_date: date, now: datetime, search_fn) -> None:
    for ev in _nr.list_events_for_date(engine, trade_date):
        done = set(ev.get("payload", {}).get("done_stages", []))
        for stage, offset in STAGE_OFFSETS.items():
            if stage in done or offset == 0:
                continue
            due_at = ev["detected_at"]
            if isinstance(due_at, str):
                continue
            if now >= due_at + timedelta(minutes=offset):
                collect_news_for_event(engine, ev, stage, now=now, search_fn=search_fn)


import os
import threading
import time
from datetime import date as _date, datetime as _datetime

POLL_SECONDS = 30


def news_enabled() -> bool:
    return str(os.getenv("SECTOR_BOARD_INTRADAY_NEWS_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}


class NewsSidecar:
    def __init__(self, *, engine, runtime, trade_date, search_fn=None, poll_seconds: int = POLL_SECONDS):
        self._engine = engine
        self._runtime = runtime
        self._trade_date = trade_date
        self._search_fn = search_fn
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self, *, now: _datetime | None = None) -> None:
        now = now or _datetime.now()
        try:
            snapshot = self._runtime.get_latest_snapshot()
        except Exception:  # noqa: BLE001
            snapshot = None
        process_snapshot_once(self._engine, snapshot, trade_date=self._trade_date,
                              now=now, top5_sectors=[], search_fn=self._search_fn)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._poll)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="news-sidecar")
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
