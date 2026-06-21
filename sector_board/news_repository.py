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
