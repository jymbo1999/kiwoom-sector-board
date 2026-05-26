from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, Table, Text, UniqueConstraint


metadata = MetaData()

sector_snapshots = Table(
    "sector_snapshots",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("snapshot_date", Date, nullable=False, index=True),
    Column("fetched_at", DateTime, nullable=False),
    Column("summary_json", Text, nullable=False, default="{}"),
    Column("themes_json", Text, nullable=False, default="[]"),
    Column("leaders_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("snapshot_date", name="uq_sector_snapshots_snapshot_date"),
)
