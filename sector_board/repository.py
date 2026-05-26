from __future__ import annotations

from datetime import date, datetime
import json
import logging
import os
import threading
from typing import Any

from flask import Flask
from sqlalchemy import Engine, create_engine, desc, inspect as sa_inspect, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .payload import normalize_snapshot_payload
from .schema import metadata, sector_snapshots

_log = logging.getLogger(__name__)

_engine_cache: dict[str, "Engine"] = {}
_engine_cache_lock = threading.Lock()


def _get_engine(database_url: str) -> "Engine":
    """Return a cached SQLAlchemy engine for the given URL (one pool per URL)."""
    normalized = normalize_database_url(database_url)
    if normalized not in _engine_cache:
        with _engine_cache_lock:
            if normalized not in _engine_cache:
                _engine_cache[normalized] = create_engine(
                    normalized,
                    future=True,
                    pool_size=2,
                    max_overflow=4,
                    pool_pre_ping=True,
                )
    return _engine_cache[normalized]


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
    return _get_engine(database_url)


def _ensure_refresh_columns(engine: Engine) -> None:
    """Add refresh tracking columns to an existing table that predates them."""
    try:
        insp = sa_inspect(engine)
        if "sector_snapshots" not in insp.get_table_names():
            return
        existing_cols = {c["name"] for c in insp.get_columns("sector_snapshots")}
        is_pg = engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            for col, col_type in [
                ("refresh_status", "VARCHAR(20)"),
                ("refresh_started_at", "TIMESTAMP"),
                ("refresh_error", "TEXT"),
            ]:
                if col not in existing_cols:
                    if is_pg:
                        conn.execute(text(
                            f"ALTER TABLE sector_snapshots ADD COLUMN IF NOT EXISTS {col} {col_type}"
                        ))
                    else:
                        conn.execute(text(
                            f"ALTER TABLE sector_snapshots ADD COLUMN {col} {col_type}"
                        ))
    except Exception as exc:
        _log.warning("[sector-board] _ensure_refresh_columns failed: %s", exc)


def ensure_schema(database_url: str | None = None, engine: Engine | None = None) -> None:
    active_engine = engine or create_snapshot_engine(database_url or "")
    metadata.create_all(active_engine, tables=[sector_snapshots], checkfirst=True)
    _ensure_refresh_columns(active_engine)


def _upsert_row(
    engine: Engine,
    full_values: dict[str, Any],
    on_conflict_updates: dict[str, Any],
) -> None:
    """Dialect-aware upsert for sector_snapshots."""
    with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            stmt = postgresql_insert(sector_snapshots).values(**full_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[sector_snapshots.c.snapshot_date],
                set_=on_conflict_updates,
            )
            conn.execute(stmt)
        elif dialect == "sqlite":
            stmt = sqlite_insert(sector_snapshots).values(**full_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[sector_snapshots.c.snapshot_date],
                set_=on_conflict_updates,
            )
            conn.execute(stmt)
        else:
            existing = conn.execute(
                select(sector_snapshots.c.id).where(
                    sector_snapshots.c.snapshot_date == full_values["snapshot_date"]
                )
            ).scalar_one_or_none()
            if existing is None:
                conn.execute(sector_snapshots.insert().values(**full_values))
            else:
                conn.execute(
                    update(sector_snapshots)
                    .where(sector_snapshots.c.id == existing)
                    .values(**on_conflict_updates)
                )


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
    full_values = {
        "snapshot_date": normalized["snapshot_date"],
        "fetched_at": normalized["generated_at"],
        "summary_json": json.dumps(normalized["summary"], ensure_ascii=False),
        "themes_json": json.dumps(normalized["themes"], ensure_ascii=False),
        "leaders_json": json.dumps(normalized["leaders"], ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
        "refresh_status": "success",
        "refresh_started_at": now,
        "refresh_error": None,
    }
    on_conflict = {
        "fetched_at": full_values["fetched_at"],
        "summary_json": full_values["summary_json"],
        "themes_json": full_values["themes_json"],
        "leaders_json": full_values["leaders_json"],
        "updated_at": now,
        "refresh_status": "success",
        "refresh_error": None,
    }
    _upsert_row(active_engine, full_values, on_conflict)
    return {
        "sector_db_status": "upserted",
        "sector_db_snapshot_date": normalized["snapshot_date"].isoformat(),
    }


def set_refresh_running(
    database_url: str | None = None,
    engine: Engine | None = None,
    snapshot_date: date | None = None,
) -> None:
    active_engine = engine or create_snapshot_engine(database_url or "")
    today = snapshot_date or date.today()
    now = datetime.now()
    full_values = {
        "snapshot_date": today,
        "fetched_at": now,
        "summary_json": "{}",
        "themes_json": "[]",
        "leaders_json": "[]",
        "created_at": now,
        "updated_at": now,
        "refresh_status": "running",
        "refresh_started_at": now,
        "refresh_error": None,
    }
    on_conflict = {
        "refresh_status": "running",
        "refresh_started_at": now,
        "refresh_error": None,
        "updated_at": now,
    }
    _upsert_row(active_engine, full_values, on_conflict)


def set_refresh_error(
    error: str,
    database_url: str | None = None,
    engine: Engine | None = None,
    snapshot_date: date | None = None,
) -> None:
    active_engine = engine or create_snapshot_engine(database_url or "")
    today = snapshot_date or date.today()
    now = datetime.now()
    full_values = {
        "snapshot_date": today,
        "fetched_at": now,
        "summary_json": "{}",
        "themes_json": "[]",
        "leaders_json": "[]",
        "created_at": now,
        "updated_at": now,
        "refresh_status": "error",
        "refresh_started_at": now,
        "refresh_error": (error or "")[:500],
    }
    on_conflict = {
        "refresh_status": "error",
        "refresh_error": (error or "")[:500],
        "updated_at": now,
    }
    _upsert_row(active_engine, full_values, on_conflict)


def _row_to_payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    m = row._mapping
    rs_raw = m.get("refresh_status")
    started_raw = m.get("refresh_started_at")
    return {
        "snapshot_date": m["snapshot_date"].isoformat(),
        "generated_at": m["fetched_at"].isoformat(timespec="seconds"),
        "summary": json.loads(m["summary_json"] or "{}"),
        "themes": json.loads(m["themes_json"] or "[]"),
        "leaders": json.loads(m["leaders_json"] or "[]"),
        "refresh_status": rs_raw or "success",
        "refresh_started_at": (
            started_raw.isoformat(timespec="seconds") if started_raw else None
        ),
        "refresh_error": m.get("refresh_error"),
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
