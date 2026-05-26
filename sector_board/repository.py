from __future__ import annotations

from datetime import date, datetime
import json
import os
from typing import Any

from flask import Flask
from sqlalchemy import Engine, create_engine, desc, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .payload import normalize_snapshot_payload
from .schema import metadata, sector_snapshots


def normalize_database_url(database_url: str) -> str:
    value = database_url.strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def resolve_database_url(app: Flask | None = None, explicit_url: str | None = None) -> str:
    if explicit_url and explicit_url.strip():
        return normalize_database_url(explicit_url)
    value = os.getenv("SECTOR_BOARD_DATABASE_URL", "").strip()
    if value:
        return normalize_database_url(value)
    if app is not None:
        value = str(app.config.get("SECTOR_BOARD_DATABASE_URL") or "").strip()
        if value:
            return normalize_database_url(value)
    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return normalize_database_url(value)
    if app is not None:
        value = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
        if value:
            return normalize_database_url(value)
    return ""


def create_snapshot_engine(database_url: str) -> Engine:
    return create_engine(normalize_database_url(database_url), future=True)


def ensure_schema(database_url: str | None = None, engine: Engine | None = None) -> None:
    active_engine = engine or create_snapshot_engine(database_url or "")
    metadata.create_all(active_engine, tables=[sector_snapshots], checkfirst=True)


def upsert_snapshot(
    payload: dict[str, Any],
    database_url: str | None = None,
    engine: Engine | None = None,
    auto_create: bool = False,
) -> dict[str, Any]:
    active_engine = engine or create_snapshot_engine(database_url or "")
    if auto_create:
        ensure_schema(engine=active_engine)

    normalized = normalize_snapshot_payload(payload)
    now = datetime.now()
    values = {
        "snapshot_date": normalized["snapshot_date"],
        "fetched_at": normalized["generated_at"],
        "summary_json": json.dumps(normalized["summary"], ensure_ascii=False),
        "themes_json": json.dumps(normalized["themes"], ensure_ascii=False),
        "leaders_json": json.dumps(normalized["leaders"], ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
    }

    with active_engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect == "postgresql":
            stmt = postgresql_insert(sector_snapshots).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[sector_snapshots.c.snapshot_date],
                set_={
                    "fetched_at": stmt.excluded.fetched_at,
                    "summary_json": stmt.excluded.summary_json,
                    "themes_json": stmt.excluded.themes_json,
                    "leaders_json": stmt.excluded.leaders_json,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            connection.execute(stmt)
        elif dialect == "sqlite":
            stmt = sqlite_insert(sector_snapshots).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[sector_snapshots.c.snapshot_date],
                set_={
                    "fetched_at": stmt.excluded.fetched_at,
                    "summary_json": stmt.excluded.summary_json,
                    "themes_json": stmt.excluded.themes_json,
                    "leaders_json": stmt.excluded.leaders_json,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            connection.execute(stmt)
        else:
            existing = connection.execute(
                select(sector_snapshots.c.id).where(
                    sector_snapshots.c.snapshot_date == values["snapshot_date"]
                )
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(sector_snapshots.insert().values(**values))
            else:
                connection.execute(
                    update(sector_snapshots)
                    .where(sector_snapshots.c.id == existing)
                    .values(
                        fetched_at=values["fetched_at"],
                        summary_json=values["summary_json"],
                        themes_json=values["themes_json"],
                        leaders_json=values["leaders_json"],
                        updated_at=values["updated_at"],
                    )
                )

    return {
        "sector_db_status": "upserted",
        "sector_db_snapshot_date": normalized["snapshot_date"].isoformat(),
    }


def _row_to_payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    mapping = row._mapping
    return {
        "snapshot_date": mapping["snapshot_date"].isoformat(),
        "generated_at": mapping["fetched_at"].isoformat(timespec="seconds"),
        "summary": json.loads(mapping["summary_json"] or "{}"),
        "themes": json.loads(mapping["themes_json"] or "[]"),
        "leaders": json.loads(mapping["leaders_json"] or "[]"),
    }


def fetch_snapshot(
    database_url: str | None = None,
    engine: Engine | None = None,
    snapshot_date: date | None = None,
) -> dict[str, Any] | None:
    active_engine = engine or create_snapshot_engine(database_url or "")
    stmt = select(sector_snapshots)
    if snapshot_date is not None:
        stmt = stmt.where(sector_snapshots.c.snapshot_date == snapshot_date)
    stmt = stmt.order_by(desc(sector_snapshots.c.snapshot_date), desc(sector_snapshots.c.fetched_at)).limit(1)
    with active_engine.connect() as connection:
        return _row_to_payload(connection.execute(stmt).first())
