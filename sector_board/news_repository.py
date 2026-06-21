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
