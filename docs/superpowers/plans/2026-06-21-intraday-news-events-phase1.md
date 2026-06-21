# Intraday 뉴스 이벤트 추적 (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인트라데이 세션 중 가격 급변 이벤트를 감지해 네이버 뉴스를 수집·영속하고, `/intraday`의 탭 UI(가격/뉴스/일일로그)와 알림 책갈피로 보여준다.

**Architecture:** 틱 루프와 분리된 사이드카 스레드가 `runtime.get_latest_snapshot()`을 30초 폴링 → 순수 감지 함수가 후보 이벤트 산출 → 공유 Postgres(로컬은 sqlite)에 이벤트/기사 영속(stage 간 `(event_id, dedupe_key)` unique dedupe). 기존 `search_naver_news`를 주입해 재사용하고, 모든 경로는 try/except로 가격판을 막지 않는다. 신규 기능은 `SECTOR_BOARD_INTRADAY_NEWS_ENABLED`(기본 OFF)로 게이팅.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy(core, dialect-aware), pytest. 대상 레포 = `kiwoom-sector-board`.

**설계 출처:** `docs/2026-06-21-intraday-news-events-phase1-design.md`

---

## File Structure

- Create `sector_board/news_schema.py` — `news_events`·`news_articles` Table 정의(공유 `metadata`) + `ensure_news_schema(engine)`.
- Create `sector_board/news_repository.py` — 엔진 헬퍼 + 이벤트/기사 upsert·조회 + unread/read + `get_storage_stats`.
- Create `sector_board/intraday_news.py` — 정규화/dedupe_key, 스냅샷 어댑터, 순수 감지, 수집 오케스트레이션, 사이드카.
- Modify `sector_board/intraday_blueprint.py` — `index`에 `tab` 분기 + 컨텍스트 주입; `api_start`/`api_stop`에 사이드카 기동/종료(게이팅).
- Modify `sector_board/templates/sector_board/intraday_live.html` — 탭 바 + 책갈피 버튼 + 뉴스/일일로그 패널.
- Create `tests/test_intraday_news_schema.py`, `tests/test_intraday_news_repository.py`, `tests/test_intraday_news_detect.py`, `tests/test_intraday_news_collect.py`, `tests/test_intraday_news_route.py`.

**공통 타입(전 태스크 합의):**
- Candidate(이벤트 후보) dict: `{event_type, scope, sector_name, stock_code, stock_name, change_rate, short_change_rate, trigger_reason}`.
- Article item dict(네이버 결과, `search_naver_news` 반환): `{title, url, excerpt, published_at, provider, ...}`.
- 임계 상수: `RISE_PCT=0.08`, `FALL_PCT=-0.08`, `SECTOR_STOCK_PCT=0.10`, `SECTOR_MIN_STOCKS=3`.
- Stage: `STAGE_OFFSETS = {"T0": 0, "T+10": 10, "T+30": 30}` (분). 이벤트당 stage 최대 3.
- 쿨다운: 이벤트 30분, 검색어 5분. 행 용량 추정 상수: `EVENT_ROW_EST=512`, `ARTICLE_ROW_EST=1024` (bytes).

---

## Task 1: 뉴스 스키마 + ensure_news_schema

**Files:**
- Create: `sector_board/news_schema.py`
- Test: `tests/test_intraday_news_schema.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_intraday_news_schema.py
from sqlalchemy import create_engine, inspect
from sector_board.news_schema import ensure_news_schema


def test_ensure_news_schema_creates_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(engine)
    names = set(inspect(engine).get_table_names())
    assert {"intraday_news_events", "intraday_news_articles"} <= names

    cols = {c["name"] for c in inspect(engine).get_columns("intraday_news_events")}
    assert {"trade_date", "event_type", "scope", "status", "is_read", "payload_json"} <= cols
    acols = {c["name"] for c in inspect(engine).get_columns("intraday_news_articles")}
    assert {"event_id", "url", "dedupe_key", "stage"} <= acols
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_schema.py -v`
Expected: FAIL (`ModuleNotFoundError: sector_board.news_schema`)

- [ ] **Step 3: 구현**

```python
# sector_board/news_schema.py
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Engine, Float, Integer,
    String, Text, Table, UniqueConstraint,
)

from .schema import metadata  # 기존 sector_snapshots 와 동일 metadata 재사용

news_events = Table(
    "intraday_news_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trade_date", Date, nullable=False, index=True),
    Column("detected_at", DateTime, nullable=False),
    Column("event_type", String(8), nullable=False),   # rise / fall
    Column("scope", String(8), nullable=False),         # stock / sector
    Column("sector_name", String(120)),
    Column("stock_code", String(20)),
    Column("stock_name", String(120)),
    Column("change_rate", Float, nullable=False, default=0.0),
    Column("short_change_rate", Float),
    Column("trigger_reason", Text),
    Column("status", String(16), nullable=False, default="detected"),
    Column("is_read", Boolean, nullable=False, default=False),
    Column("payload_json", Text),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
    extend_existing=True,
)

news_articles = Table(
    "intraday_news_articles", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, nullable=False, index=True),
    Column("title", Text),
    Column("url", Text),
    Column("source", String(60)),
    Column("published_at", String(40)),
    Column("description", Text),
    Column("query", Text),
    Column("stage", String(8)),
    Column("dedupe_key", String(80), nullable=False),
    Column("collected_at", DateTime),
    Column("created_at", DateTime),
    UniqueConstraint("event_id", "dedupe_key", name="uq_news_article_event_dedupe"),
    extend_existing=True,
)


def ensure_news_schema(engine: Engine) -> None:
    """뉴스 테이블만 생성(존재하면 무시). 기존 sector_snapshots 는 건드리지 않음."""
    metadata.create_all(engine, tables=[news_events, news_articles], checkfirst=True)
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_schema.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/news_schema.py tests/test_intraday_news_schema.py
git commit -m "feat(news): intraday news events/articles 스키마 추가"
```

---

## Task 2: 제목 정규화 + dedupe_key

**Files:**
- Create: `sector_board/intraday_news.py`
- Test: `tests/test_intraday_news_detect.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_intraday_news_detect.py
from sector_board.intraday_news import normalize_title, article_dedupe_key


def test_normalize_title_strips_and_lowers():
    assert normalize_title("<b>로봇주</b> 급등! (특징주)") == "로봇주급등특징주"


def test_dedupe_key_prefers_url():
    item = {"title": "A", "url": "http://x/1", "published_at": "2026-06-21", "provider": "Naver"}
    assert article_dedupe_key(item) == "url:http://x/1"


def test_dedupe_key_falls_back_to_title_hash():
    item = {"title": "로봇주 급등", "url": "", "published_at": "2026-06-21", "provider": "Naver"}
    key = article_dedupe_key(item)
    assert key.startswith("h:") and len(key) > 10
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_detect.py -v`
Expected: FAIL (`ModuleNotFoundError: sector_board.intraday_news`)

- [ ] **Step 3: 구현 (파일 시작부)**

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_detect.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/intraday_news.py tests/test_intraday_news_detect.py
git commit -m "feat(news): 제목 정규화 + dedupe_key 헬퍼"
```

---

## Task 3: 스냅샷 어댑터 + 순수 감지 함수

**Files:**
- Modify: `sector_board/intraday_news.py`
- Test: `tests/test_intraday_news_detect.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/test_intraday_news_detect.py (이어서 추가)
from sector_board.intraday_news import extract_movers_from_snapshot, detect_intraday_news_events


def _snap():
    return {
        "leaders": [
            {"base_code": "277810", "name": "레인보우로보틱스", "sector_name": "로봇", "last_change_rate": 0.12},
            {"base_code": "454910", "name": "두산로보틱스", "sector_name": "로봇", "last_change_rate": 0.11},
            {"base_code": "058610", "name": "에스피지", "sector_name": "로봇", "last_change_rate": 0.10},
            {"base_code": "000001", "name": "잔잔주", "sector_name": "기타", "last_change_rate": 0.01},
        ],
        "sectors": [{"sector_name": "로봇", "average_change_rate": 0.11}],
    }


def test_extract_movers_tolerant_keys():
    movers = extract_movers_from_snapshot(_snap())
    assert movers["leaders"][0]["stock_code"] == "277810"
    assert movers["leaders"][0]["change_rate"] == 0.12


def test_detect_stock_rise_event():
    cands = detect_intraday_news_events(_snap(), top5_sectors=[])
    rises = [c for c in cands if c["scope"] == "stock" and c["event_type"] == "rise"]
    assert any(c["stock_code"] == "277810" for c in rises)
    assert all(c["stock_code"] != "000001" for c in rises)  # +1% 는 임계 미달


def test_detect_sector_event_three_strong_stocks():
    cands = detect_intraday_news_events(_snap(), top5_sectors=[])
    sector = [c for c in cands if c["scope"] == "sector"]
    assert any(c["sector_name"] == "로봇" for c in sector)
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_detect.py -v`
Expected: FAIL (`extract_movers_from_snapshot` 미정의)

- [ ] **Step 3: 구현 추가 (intraday_news.py 끝에)**

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_detect.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/intraday_news.py tests/test_intraday_news_detect.py
git commit -m "feat(news): 스냅샷 어댑터 + 순수 이벤트 감지"
```

---

## Task 4: 이벤트 upsert (30분 쿨다운)

**Files:**
- Create: `sector_board/news_repository.py`
- Test: `tests/test_intraday_news_repository.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_intraday_news_repository.py
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(eng)
    return eng


def _cand():
    return {
        "event_type": "rise", "scope": "stock", "sector_name": "로봇",
        "stock_code": "277810", "stock_name": "레인보우로보틱스",
        "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x",
    }


def test_upsert_event_creates_then_cooldown_updates(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    id1 = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    # 5분 뒤 같은 종목+타입 → 신규 없음(쿨다운), 같은 id 갱신
    id2 = nr.upsert_event(eng, {**_cand(), "change_rate": 0.15}, trade_date=date(2026, 6, 21), now=t0 + timedelta(minutes=5))
    assert id1 == id2
    assert len(nr.list_events_for_date(eng, date(2026, 6, 21))) == 1


def test_upsert_event_new_after_cooldown(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0 + timedelta(minutes=31))
    assert len(nr.list_events_for_date(eng, date(2026, 6, 21))) == 2
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py -v`
Expected: FAIL (`ModuleNotFoundError: sector_board.news_repository`)

- [ ] **Step 3: 구현**

```python
# sector_board/news_repository.py
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, func, select, text, update

from .news_schema import news_articles, news_events

COOLDOWN_MIN = 30


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row._mapping)
    if d.get("payload_json"):
        try:
            d["payload"] = json.loads(d["payload_json"])
        except (TypeError, ValueError):
            d["payload"] = {}
    else:
        d["payload"] = {}
    return d


def upsert_event(engine: Engine, candidate: dict[str, Any], *, trade_date: date, now: datetime) -> int:
    key_col = news_events.c.stock_code if candidate["scope"] == "stock" else news_events.c.sector_name
    key_val = candidate["stock_code"] if candidate["scope"] == "stock" else candidate["sector_name"]
    cutoff = now - timedelta(minutes=COOLDOWN_MIN)
    with engine.begin() as conn:
        existing = conn.execute(
            select(news_events.c.id)
            .where(and_(
                news_events.c.trade_date == trade_date,
                news_events.c.scope == candidate["scope"],
                news_events.c.event_type == candidate["event_type"],
                key_col == key_val,
                news_events.c.detected_at >= cutoff,
            ))
            .order_by(news_events.c.detected_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            conn.execute(
                update(news_events).where(news_events.c.id == existing).values(
                    change_rate=candidate["change_rate"], updated_at=now,
                )
            )
            return int(existing)
        result = conn.execute(news_events.insert().values(
            trade_date=trade_date, detected_at=now,
            event_type=candidate["event_type"], scope=candidate["scope"],
            sector_name=candidate.get("sector_name"), stock_code=candidate.get("stock_code"),
            stock_name=candidate.get("stock_name"), change_rate=candidate["change_rate"],
            short_change_rate=candidate.get("short_change_rate"),
            trigger_reason=candidate.get("trigger_reason"), status="detected",
            is_read=False, payload_json=json.dumps({"done_stages": []}),
            created_at=now, updated_at=now,
        ))
        return int(result.inserted_primary_key[0])


def list_events_for_date(engine: Engine, trade_date: date) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(news_events).where(news_events.c.trade_date == trade_date)
            .order_by(news_events.c.detected_at.desc())
        ).all()
    return [_row_to_dict(r) for r in rows]
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/news_repository.py tests/test_intraday_news_repository.py
git commit -m "feat(news): 이벤트 upsert + 30분 쿨다운"
```

---

## Task 5: 기사 insert (event_id+dedupe_key unique) + 조회

**Files:**
- Modify: `sector_board/news_repository.py`
- Test: `tests/test_intraday_news_repository.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/test_intraday_news_repository.py (이어서)
def test_insert_article_dedupes(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    a = {"title": "로봇주 급등", "url": "http://x/1", "source": "Naver",
         "published_at": "2026-06-21", "description": "", "query": "q", "stage": "T0",
         "dedupe_key": "url:http://x/1"}
    assert nr.insert_article(eng, ev, a, now=t0) is True
    assert nr.insert_article(eng, ev, a, now=t0) is False  # 중복
    assert len(nr.list_articles_for_event(eng, ev)) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py::test_insert_article_dedupes -v`
Expected: FAIL (`insert_article` 미정의)

- [ ] **Step 3: 구현 추가 (news_repository.py 끝)**

```python
from sqlalchemy.exc import IntegrityError


def insert_article(engine: Engine, event_id: int, article: dict[str, Any], *, now: datetime) -> bool:
    """삽입 성공 True, (event_id,dedupe_key) 중복이면 False."""
    try:
        with engine.begin() as conn:
            conn.execute(news_articles.insert().values(
                event_id=event_id, title=article.get("title"), url=article.get("url"),
                source=article.get("source") or article.get("provider"),
                published_at=article.get("published_at"), description=article.get("description") or article.get("excerpt"),
                query=article.get("query"), stage=article.get("stage"),
                dedupe_key=article["dedupe_key"], collected_at=now, created_at=now,
            ))
        return True
    except IntegrityError:
        return False


def list_articles_for_event(engine: Engine, event_id: int) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(news_articles).where(news_articles.c.event_id == event_id)
            .order_by(news_articles.c.collected_at.desc())
        ).all()
    return [dict(r._mapping) for r in rows]


def set_event_status(engine: Engine, event_id: int, status: str, *, now: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(update(news_events).where(news_events.c.id == event_id)
                     .values(status=status, updated_at=now))


def mark_stage_done(engine: Engine, event_id: int, stage: str, *, now: datetime) -> None:
    with engine.begin() as conn:
        row = conn.execute(select(news_events.c.payload_json).where(news_events.c.id == event_id)).scalar_one_or_none()
        payload = {}
        if row:
            try:
                payload = json.loads(row)
            except (TypeError, ValueError):
                payload = {}
        done = set(payload.get("done_stages", []))
        done.add(stage)
        payload["done_stages"] = sorted(done)
        conn.execute(update(news_events).where(news_events.c.id == event_id)
                     .values(payload_json=json.dumps(payload), updated_at=now))
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add sector_board/news_repository.py tests/test_intraday_news_repository.py
git commit -m "feat(news): 기사 insert dedupe + 상태/stage 갱신"
```

---

## Task 6: unread/read + 날짜목록 + 용량 통계

**Files:**
- Modify: `sector_board/news_repository.py`
- Test: `tests/test_intraday_news_repository.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/test_intraday_news_repository.py (이어서)
def test_unread_and_mark_read(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    assert nr.count_unread(eng, date(2026, 6, 21)) == 1
    nr.mark_read(eng, date(2026, 6, 21), now=t0)
    assert nr.count_unread(eng, date(2026, 6, 21)) == 0


def test_storage_stats(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    nr.insert_article(eng, ev, {"title": "t", "url": "http://x/1", "dedupe_key": "url:http://x/1", "stage": "T0"}, now=t0)
    stats = nr.get_storage_stats(eng)
    assert stats["total_events"] == 1
    assert stats["total_articles"] == 1
    assert stats["total_bytes"] > 0
    assert isinstance(stats["total_human"], str)
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py::test_storage_stats -v`
Expected: FAIL (`count_unread`/`get_storage_stats` 미정의)

- [ ] **Step 3: 구현 추가**

```python
EVENT_ROW_EST = 512
ARTICLE_ROW_EST = 1024


def count_unread(engine: Engine, trade_date: date) -> int:
    with engine.begin() as conn:
        return int(conn.execute(
            select(func.count()).select_from(news_events).where(and_(
                news_events.c.trade_date == trade_date, news_events.c.is_read == False,  # noqa: E712
            ))
        ).scalar_one())


def mark_read(engine: Engine, trade_date: date, *, now: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(update(news_events).where(news_events.c.trade_date == trade_date)
                     .values(is_read=True, updated_at=now))


def list_event_dates(engine: Engine) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(news_events.c.trade_date, func.count().label("event_count"))
            .group_by(news_events.c.trade_date).order_by(news_events.c.trade_date.desc())
        ).all()
    return [{"trade_date": r[0], "event_count": int(r[1])} for r in rows]


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1.0:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def get_storage_stats(engine: Engine) -> dict[str, Any]:
    with engine.begin() as conn:
        n_events = int(conn.execute(select(func.count()).select_from(news_events)).scalar_one())
        n_articles = int(conn.execute(select(func.count()).select_from(news_articles)).scalar_one())
        dialect = conn.dialect.name
        total_bytes = 0
        if dialect == "postgresql":
            try:
                total_bytes = int(conn.execute(text(
                    "SELECT pg_total_relation_size('intraday_news_events') "
                    "+ pg_total_relation_size('intraday_news_articles')"
                )).scalar_one())
            except Exception:  # noqa: BLE001
                total_bytes = n_events * EVENT_ROW_EST + n_articles * ARTICLE_ROW_EST
        else:
            total_bytes = n_events * EVENT_ROW_EST + n_articles * ARTICLE_ROW_EST
    human = _human_bytes(float(total_bytes))
    return {"total_events": n_events, "total_articles": n_articles,
            "total_bytes": total_bytes, "total_human": human}
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_repository.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add sector_board/news_repository.py tests/test_intraday_news_repository.py
git commit -m "feat(news): unread/read + 날짜목록 + 용량 통계"
```

---

## Task 7: 수집 오케스트레이션 (search_fn 주입, stage/쿼리 쿨다운)

**Files:**
- Modify: `sector_board/intraday_news.py`
- Test: `tests/test_intraday_news_collect.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_intraday_news_collect.py
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr
from sector_board.intraday_news import collect_news_for_event


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(eng)
    return eng


def _fake_search(query, display=10, stock_name=None):
    return [{"title": "로봇주 급등", "url": "http://x/1", "provider": "Naver",
             "published_at": "2026-06-21", "excerpt": "내용"}]


def test_collect_stores_then_dedupes_across_stages(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": "로봇",
                               "stock_code": "277810", "stock_name": "레인보우로보틱스",
                               "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                         trade_date=date(2026, 6, 21), now=t0)
    event = nr.list_events_for_date(eng, date(2026, 6, 21))[0]
    added0 = collect_news_for_event(eng, event, "T0", now=t0, search_fn=_fake_search)
    added10 = collect_news_for_event(eng, event, "T+10", now=t0 + timedelta(minutes=10), search_fn=_fake_search)
    assert added0 == 1
    assert added10 == 0  # 같은 기사 → dedupe
    assert len(nr.list_articles_for_event(eng, ev)) == 1


def test_collect_handles_search_failure(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": None,
                               "stock_code": "277810", "stock_name": "레인보우로보틱스",
                               "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                         trade_date=date(2026, 6, 21), now=t0)
    event = nr.list_events_for_date(eng, date(2026, 6, 21))[0]

    def boom(*a, **k):
        raise RuntimeError("naver down")

    assert collect_news_for_event(eng, event, "T0", now=t0, search_fn=boom) == 0  # 예외 삼킴
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py -v`
Expected: FAIL (`collect_news_for_event` 미정의)

- [ ] **Step 3: 구현 추가 (intraday_news.py 끝)**

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/intraday_news.py tests/test_intraday_news_collect.py
git commit -m "feat(news): 이벤트 뉴스 수집 오케스트레이션(주입형 검색)"
```

---

## Task 8: 1회 처리 루프 (감지→upsert→T0 수집) + due-stage 처리

**Files:**
- Modify: `sector_board/intraday_news.py`
- Test: `tests/test_intraday_news_collect.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/test_intraday_news_collect.py (이어서)
from sector_board.intraday_news import process_snapshot_once


def _snap():
    return {"leaders": [{"base_code": "277810", "name": "레인보우로보틱스",
                         "sector_name": "로봇", "last_change_rate": 0.12}],
            "sectors": [{"sector_name": "로봇", "average_change_rate": 0.12}]}


def test_process_snapshot_once_creates_event_and_collects(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    process_snapshot_once(eng, _snap(), trade_date=date(2026, 6, 21), now=t0,
                          top5_sectors=[], search_fn=_fake_search)
    events = nr.list_events_for_date(eng, date(2026, 6, 21))
    assert len(events) >= 1
    stock_ev = [e for e in events if e["stock_code"] == "277810"][0]
    assert len(nr.list_articles_for_event(eng, stock_ev["id"])) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py::test_process_snapshot_once_creates_event_and_collects -v`
Expected: FAIL (`process_snapshot_once` 미정의)

- [ ] **Step 3: 구현 추가**

```python
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
```

이 태스크는 `_nr.list_events_for_date_any` 헬퍼가 필요하다. `news_repository.py`에 추가:

```python
def list_events_for_date_any(engine: Engine, event_id: int) -> list[dict[str, Any]]:
    """단일 이벤트를 payload 포함 dict 리스트(0/1개)로 반환."""
    with engine.begin() as conn:
        rows = conn.execute(select(news_events).where(news_events.c.id == event_id)).all()
    return [_row_to_dict(r) for r in rows]
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/intraday_news.py sector_board/news_repository.py tests/test_intraday_news_collect.py
git commit -m "feat(news): 스냅샷 1회 처리 + due-stage 보강"
```

---

## Task 9: 사이드카 스레드 (게이팅, 시작/종료)

**Files:**
- Modify: `sector_board/intraday_news.py`
- Test: `tests/test_intraday_news_collect.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/test_intraday_news_collect.py (이어서)
import os
from sector_board.intraday_news import news_enabled, NewsSidecar


def test_news_enabled_env(monkeypatch):
    monkeypatch.delenv("SECTOR_BOARD_INTRADAY_NEWS_ENABLED", raising=False)
    assert news_enabled() is False
    monkeypatch.setenv("SECTOR_BOARD_INTRADAY_NEWS_ENABLED", "1")
    assert news_enabled() is True


def test_sidecar_run_once(tmp_path):
    eng = _engine(tmp_path)

    class FakeRuntime:
        def get_latest_snapshot(self):
            return _snap()

    sc = NewsSidecar(engine=eng, runtime=FakeRuntime(),
                     trade_date=date(2026, 6, 21), search_fn=_fake_search)
    sc.run_once(now=datetime(2026, 6, 21, 9, 18))
    assert len(nr.list_events_for_date(eng, date(2026, 6, 21))) >= 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py::test_sidecar_run_once -v`
Expected: FAIL (`NewsSidecar` 미정의)

- [ ] **Step 3: 구현 추가**

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_collect.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sector_board/intraday_news.py tests/test_intraday_news_collect.py
git commit -m "feat(news): 사이드카 스레드 + 게이팅"
```

---

## Task 10: 블루프린트 탭 + 컨텍스트 주입

**Files:**
- Modify: `sector_board/intraday_blueprint.py` (`index`, `api_start`, `api_stop`)
- Test: `tests/test_intraday_news_route.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_intraday_news_route.py
from datetime import date, datetime

from flask import Flask
from sqlalchemy import create_engine
from sector_board import register_sector_board, register_intraday
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr


def _app(tmp_path):
    app = Flask(__name__)
    db_url = f"sqlite:///{tmp_path/'news.db'}"
    app.config["SECTOR_BOARD_DATABASE_URL"] = db_url
    app.config["SECTOR_BOARD_LAYOUT_TEMPLATE"] = "sector_board/standalone.html"
    register_sector_board(app)
    register_intraday(app)
    eng = create_engine(db_url, future=True)
    ensure_news_schema(eng)
    nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": "로봇",
                          "stock_code": "277810", "stock_name": "레인보우로보틱스",
                          "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                    trade_date=date.today(), now=datetime.now())
    return app


def test_news_tab_renders(tmp_path):
    app = _app(tmp_path)
    c = app.test_client()
    assert c.get("/intraday").status_code == 200            # 기본 price
    r = c.get("/intraday?tab=news")
    assert r.status_code == 200
    assert "레인보우로보틱스" in r.get_data(as_text=True)
    r2 = c.get("/intraday?tab=daily-log")
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert "총 이벤트" in body and "전체 용량" in body
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_route.py -v`
Expected: FAIL (탭/패널 없음 → "총 이벤트" 미존재)

- [ ] **Step 3: `index` 수정 — `request.args['tab']` 분기 + 컨텍스트 주입**

`sector_board/intraday_blueprint.py` 상단 import에 추가:

```python
from datetime import date as _date, datetime as _datetime
from flask import request
from sector_board import news_repository as _news_repo
from sector_board.news_schema import ensure_news_schema as _ensure_news_schema
from sector_board.intraday_news import news_enabled as _news_enabled
from sector_board.repository import create_snapshot_engine, resolve_database_url
```

`index()` 함수를 아래로 교체:

```python
    @blueprint.route("/", strict_slashes=False)
    def index():
        """장중 리더보드 HTML (1초 polling 기반) + 뉴스/일일로그 탭."""
        runtime = _get_runtime()
        runtime_state = runtime.get_status()["state"] if runtime else "not_running"
        tab = (request.args.get("tab") or "price").strip()

        news_ctx = {"events": [], "stats": None, "dates": [], "unread": 0, "tab": tab}
        try:
            db_url = resolve_database_url(current_app)
            if db_url:
                engine = create_snapshot_engine(db_url)
                _ensure_news_schema(engine)
                today = _date.today()
                news_ctx["unread"] = _news_repo.count_unread(engine, today)
                if tab == "news":
                    news_ctx["events"] = _news_repo.list_events_for_date(engine, today)
                    for ev in news_ctx["events"]:
                        ev["articles"] = _news_repo.list_articles_for_event(engine, ev["id"])
                    _news_repo.mark_read(engine, today, now=_datetime.now())
                    news_ctx["unread"] = 0
                elif tab == "daily-log":
                    news_ctx["stats"] = _news_repo.get_storage_stats(engine)
                    news_ctx["dates"] = _news_repo.list_event_dates(engine)
        except Exception:  # noqa: BLE001  (뉴스 실패가 가격판을 막지 않게)
            pass

        return render_template(
            "sector_board/intraday_live.html",
            layout_template="sector_board/standalone.html",
            runtime_state=runtime_state,
            news=news_ctx,
        )
```

`api_start()`의 `_set_runtime(runtime, metadata)` 바로 다음에 사이드카 기동 추가:

```python
        _set_runtime(runtime, metadata)

        # 뉴스 사이드카 (게이팅; 실패해도 인트라데이 시작은 정상)
        try:
            if _news_enabled():
                from sector_board.intraday_news import NewsSidecar
                db_url = resolve_database_url(current_app)
                if db_url:
                    engine = create_snapshot_engine(db_url)
                    _ensure_news_schema(engine)
                    sidecar = NewsSidecar(engine=engine, runtime=runtime, trade_date=_date.today())
                    sidecar.start()
                    current_app.config["_NEWS_SIDECAR"] = sidecar
        except Exception:  # noqa: BLE001
            pass
```

`api_stop()`의 함수 본문 시작 직후(runtime 정지 전후)에 사이드카 종료 추가:

```python
        sidecar = current_app.config.pop("_NEWS_SIDECAR", None)
        if sidecar is not None:
            try:
                sidecar.stop()
            except Exception:  # noqa: BLE001
                pass
```

- [ ] **Step 4: 템플릿 탭/패널 추가** — `sector_board/templates/sector_board/intraday_live.html`

기존 `{% block content %}` 최상단(가격판 마크업 바로 위)에 탭 바와 책갈피 버튼 삽입, 그리고 뉴스/일일로그 패널을 `news.tab` 값으로 조건 렌더한다. 아래 블록을 content 시작부에 추가:

```html
<div class="news-tabbar" style="display:flex;gap:8px;align-items:center;margin-bottom:14px;">
  <a href="?tab=price"     class="btn {% if news.tab == 'price' %}btn-primary{% else %}btn-secondary{% endif %}">실시간 가격</a>
  <a href="?tab=news"      class="btn {% if news.tab == 'news' %}btn-primary{% else %}btn-secondary{% endif %}">
    뉴스 이벤트{% if news.unread and news.unread > 0 %} <span style="color:#ef4444;font-weight:800;">! {{ news.unread }}</span>{% endif %}
  </a>
  <a href="?tab=daily-log" class="btn {% if news.tab == 'daily-log' %}btn-primary{% else %}btn-secondary{% endif %}">일일 로그</a>
  <a href="?tab=news" style="margin-left:auto;" class="btn btn-secondary" title="뉴스 이벤트 바로가기">
    🔖 뉴스 이벤트{% if news.unread and news.unread > 0 %} <strong style="color:#ef4444;">!</strong>{% endif %}
  </a>
</div>

{% if news.tab == 'news' %}
  <div class="card"><div class="card-body">
    <h2>오늘의 뉴스 이벤트</h2>
    {% if not news.events %}<p>아직 감지된 이벤트가 없습니다.</p>{% endif %}
    {% for ev in news.events %}
      <div class="card mb-4"><div class="card-body">
        <strong>{{ ev.detected_at }} · {{ '급등' if ev.event_type == 'rise' else '급락' }}</strong>
        · {{ ev.sector_name or ev.stock_name or '' }}
        {% if ev.stock_name %}<span>({{ ev.stock_name }})</span>{% endif %}
        <div>감지 사유: {{ ev.trigger_reason }} · 등락률 {{ '%.1f'|format(ev.change_rate * 100) }}%</div>
        <div>수집 기사: {{ ev.articles|length }}개 · 상태: {{ ev.status }}</div>
        <ul>
          {% for a in ev.articles %}
            <li><a href="{{ a.url }}" target="_blank" rel="noopener">{{ a.title }}</a> <small>{{ a.published_at }}</small></li>
          {% endfor %}
        </ul>
      </div></div>
    {% endfor %}
  </div></div>

{% elif news.tab == 'daily-log' %}
  <div class="card"><div class="card-body">
    <h2>일일 로그</h2>
    {% if news.stats %}
      <p>총 이벤트 {{ news.stats.total_events }}건 · 총 기사 {{ news.stats.total_articles }}개 · 전체 용량 {{ news.stats.total_human }}</p>
    {% endif %}
    <table class="table table-sm">
      <thead><tr><th>날짜</th><th>이벤트 수</th></tr></thead>
      <tbody>
        {% for row in news.dates %}<tr><td>{{ row.trade_date }}</td><td>{{ row.event_count }}</td></tr>{% endfor %}
      </tbody>
    </table>
  </div></div>

{% else %}
  {# tab == price: 기존 가격판 마크업은 이 블록 아래 그대로 둔다 #}
{% endif %}
```

> 주의: 기존 가격판 마크업은 **삭제하지 말 것.** 위 블록을 추가하고, 가격판 전체를 `{% if news.tab == 'price' %} ... {% endif %}`로 감싸거나, 위 `{% else %}` 분기 안에 들어가도록 배치한다. price 탭에서만 가격판이 보이면 됨.

- [ ] **Step 5: 통과 확인 + 커밋**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest tests/test_intraday_news_route.py -v`
Expected: PASS

```bash
git add sector_board/intraday_blueprint.py sector_board/templates/sector_board/intraday_live.html tests/test_intraday_news_route.py
git commit -m "feat(news): /intraday 탭(가격/뉴스/일일로그) + 책갈피 + 용량 패널"
```

---

## Task 11: 전체 회귀 + 호스트 env 노출

**Files:**
- Modify: `/Users/haesungjun/VSCODE Library/flask-star-admin-master/render.yaml`

- [ ] **Step 1: 섹터보드 전체 테스트 회귀**

Run: `cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board" && .venv/bin/python -m pytest -q`
Expected: 기존 테스트 + 신규 5개 파일 모두 PASS (실패 시 해당 태스크로 복귀해 수정)

- [ ] **Step 2: 호스트 render.yaml에 env 추가 (기본 ON으로 켤지 결정 — 기본은 명시적으로 "1")**

`render.yaml`의 `ENABLE_BATTERY_MODULE` 블록 다음에 추가:

```yaml
      - key: SECTOR_BOARD_INTRADAY_NEWS_ENABLED
        value: "1"
```

> 네이버 키(`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`)가 Render env에 있어야 실제 기사 수집됨. 없으면 이벤트만 기록되고 기사 0개(정상).

- [ ] **Step 3: 커밋 (host 레포)**

```bash
cd "/Users/haesungjun/VSCODE Library/flask-star-admin-master"
git add render.yaml
git commit -m "chore(sector): intraday 뉴스 이벤트 기능 env 노출"
```

- [ ] **Step 4: 섹터보드 레포 push (Render 배포 트리거)**

```bash
cd "/Users/haesungjun/VSCODE Library/kiwoom-sector-board"
git push origin master
```

> push 후 Render가 `@master` 재빌드. 배포 후 `/sector-board/intraday`에서 세션 start → 급등 시 뉴스 탭 NEW 확인.

---

## Self-Review 메모 (작성자 확인 완료)
- **Spec 커버리지:** 감지(Task3)·쿨다운(Task4)·dedupe(Task5)·용량패널(Task6/10)·수집 stage(Task7/8)·사이드카 게이팅(Task9)·탭/책갈피/NEW(Task10)·비파괴 env(Task9/11) — 스펙 §2~§10 전부 태스크 매핑됨.
- **Phase 경계:** OpenAI 요약·호출예산/429·16:10 최종요약은 의도적으로 제외(Phase 2/4). 일일로그는 요약 없이 집계만.
- **타입 일관성:** `upsert_event(engine, candidate, *, trade_date, now)`, `collect_news_for_event(engine, event, stage, *, now, search_fn)`, `process_snapshot_once(...)`, `NewsSidecar(engine=, runtime=, trade_date=, search_fn=)` — 전 태스크 동일 시그니처 사용.
- **알려진 주의:** `intraday_live.html`의 기존 가격판을 price 탭으로 감싸는 작업은 수작업 배치 필요(Task10 Step4 주의 참고) — 실행자는 기존 마크업을 보존하며 조건부로 감쌀 것.
