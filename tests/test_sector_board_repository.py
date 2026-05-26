from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from sector_board.repository import create_snapshot_engine, ensure_schema, fetch_snapshot, upsert_snapshot
from sector_board.schema import sector_snapshots


def _payload(name: str, generated_at: str = "2026-05-26T09:05:00") -> dict:
    return {
        "generated_at": generated_at,
        "summary": {
            "theme_count": 1,
            "stock_count": 2,
            "top_theme": name,
            "avg_change_rate": 3.2,
        },
        "themes": [
            {
                "theme_id": name,
                "theme_name": name,
                "theme_score": 92.5,
                "total_trading_value": 150_000_000_000,
                "top5_change_rate_mean": 6.5,
                "leader_labels": "A (+7.00%)",
            }
        ],
        "leaders": [
            {
                "theme_id": name,
                "rank": 1,
                "name": "A",
                "code": "000001",
                "change_rate": 7.0,
                "trade_value": 80_000_000_000,
            }
        ],
    }


def test_upsert_snapshot_keeps_one_row_per_day(tmp_path) -> None:
    engine = create_snapshot_engine(f"sqlite:///{tmp_path / 'sector.db'}")
    ensure_schema(engine=engine)

    upsert_snapshot(_payload("AI"), engine=engine)
    upsert_snapshot(_payload("Robot", generated_at="2026-05-26T10:00:00"), engine=engine)

    with engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(sector_snapshots)).scalar_one()

    snapshot = fetch_snapshot(engine=engine, snapshot_date=datetime(2026, 5, 26).date())

    assert count == 1
    assert snapshot is not None
    assert snapshot["summary"]["top_theme"] == "Robot"
    assert snapshot["themes"][0]["theme_name"] == "Robot"


def test_fetch_snapshot_returns_none_when_missing(tmp_path) -> None:
    engine = create_snapshot_engine(f"sqlite:///{tmp_path / 'sector.db'}")
    ensure_schema(engine=engine)

    assert fetch_snapshot(engine=engine, snapshot_date=datetime(2026, 5, 26).date()) is None
