from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_generated_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value is None:
        return datetime.now()
    text = str(value).strip()
    if not text:
        return datetime.now()
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def normalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    generated_at = parse_generated_at(payload.get("generated_at"))
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    themes = payload.get("themes") if isinstance(payload.get("themes"), list) else []
    leaders = payload.get("leaders") if isinstance(payload.get("leaders"), list) else []
    snapshot_date = payload.get("snapshot_date")
    if isinstance(snapshot_date, date):
        day = snapshot_date
    elif snapshot_date:
        day = date.fromisoformat(str(snapshot_date)[:10])
    else:
        day = generated_at.date()

    return {
        "generated_at": generated_at,
        "snapshot_date": day,
        "summary": summary,
        "themes": themes,
        "leaders": leaders,
    }
