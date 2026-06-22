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
