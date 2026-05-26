from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    safe = frame.copy()
    return json.loads(safe.to_json(orient="records", force_ascii=False))


def build_morning_snapshot_payload(
    summary: dict[str, Any],
    heatmap: pd.DataFrame,
    leaders: pd.DataFrame,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now()
    return {
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "summary": summary,
        "themes": _records(heatmap),
        "leaders": _records(leaders),
    }


def persist_morning_snapshot(
    summary: dict[str, Any],
    heatmap: pd.DataFrame,
    leaders: pd.DataFrame,
    generated_at: datetime | None = None,
) -> dict[str, str]:
    """Persist the current board locally, then optionally upload the JSON to Cloudflare R2."""

    timestamp = generated_at or datetime.now()
    payload = build_morning_snapshot_payload(summary, heatmap, leaders, timestamp)
    day_dir = SNAPSHOT_DIR / timestamp.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    filename = f"morning-board-{timestamp.strftime('%H%M%S')}.json"
    local_path = day_dir / filename
    local_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {"local_path": str(local_path)}
    sector_db_result = _persist_snapshot_to_sector_board_db(payload)
    if sector_db_result:
        result.update(sector_db_result)
    r2_result = _upload_snapshot_to_r2(filename=f"{timestamp.strftime('%Y-%m-%d')}/{filename}", payload=payload)
    if r2_result:
        result.update(r2_result)
    return result


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _persist_snapshot_to_sector_board_db(payload: dict[str, Any]) -> dict[str, str]:
    database_url = os.getenv("SECTOR_BOARD_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {}

    try:
        from sector_board.repository import resolve_database_url, upsert_snapshot
    except ModuleNotFoundError as exc:
        return {"sector_db_status": f"dependency-missing:{exc.name}"}

    try:
        return upsert_snapshot(
            payload,
            database_url=resolve_database_url(explicit_url=database_url),
            auto_create=_truthy_env("SECTOR_BOARD_AUTO_CREATE_TABLE"),
        )
    except Exception as exc:
        return {"sector_db_status": f"error:{exc}"}


def _upload_snapshot_to_r2(filename: str, payload: dict[str, Any]) -> dict[str, str]:
    bucket = os.getenv("R2_BUCKET", "").strip()
    endpoint_url = os.getenv("AWS_ENDPOINT_URL", "").strip()
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    if not all([bucket, endpoint_url, access_key, secret_key]):
        return {}

    try:
        import boto3
    except ModuleNotFoundError:
        return {"r2_status": "boto3-not-installed"}

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("AWS_REGION", "auto"),
    )
    key = f"morning-board/{filename}"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )
    return {"r2_status": "uploaded", "r2_key": key}


def load_latest_snapshot(date: datetime | None = None) -> dict[str, Any] | None:
    """Return the most recent morning-board snapshot for the given date, or None."""
    target = (date or datetime.now()).strftime("%Y-%m-%d")
    day_dir = SNAPSHOT_DIR / target
    if not day_dir.exists():
        return None
    files = sorted(day_dir.glob("morning-board-*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_morning_view_models_from_snapshot(
    max_age_seconds: int = 90,
) -> tuple[dict, pd.DataFrame, pd.DataFrame] | None:
    """Return (summary, heatmap, leaders) from the latest snapshot if it is fresh enough.

    Returns None when no snapshot exists or it is older than max_age_seconds.
    """
    snapshot = load_latest_snapshot()
    if snapshot is None:
        return None
    try:
        generated_at = datetime.fromisoformat(snapshot.get("generated_at", ""))
    except ValueError:
        return None
    if (datetime.now() - generated_at).total_seconds() > max_age_seconds:
        return None
    summary = snapshot.get("summary", {})
    heatmap = pd.DataFrame(snapshot.get("themes", []))
    leaders = pd.DataFrame(snapshot.get("leaders", []))
    return summary, heatmap, leaders


def load_yesterday_heatmap(reference: datetime | None = None) -> pd.DataFrame:
    """Return the heatmap DataFrame from yesterday's latest snapshot, or empty DataFrame."""
    yesterday = (reference or datetime.now()) - timedelta(days=1)
    payload = load_latest_snapshot(yesterday)
    if not payload or not payload.get("themes"):
        return pd.DataFrame()
    return pd.DataFrame(payload["themes"])


def compute_rank_changes(
    today_heatmap: pd.DataFrame,
    yesterday_heatmap: pd.DataFrame,
    sector_limit: int = 12,
) -> dict[str, str]:
    """Return {theme_name: label} where label is '▲N', '▼N', '=', or 'NEW'.

    Compares the top `sector_limit` sectors between today and yesterday.
    """
    if today_heatmap.empty:
        return {}

    today_ranked = (
        today_heatmap.sort_values(["theme_score", "total_trading_value"], ascending=[False, False])
        .head(sector_limit)
        .reset_index(drop=True)
    )
    today_ranks = {str(row["theme_name"]): i + 1 for i, row in today_ranked.iterrows()}

    if yesterday_heatmap.empty or "theme_name" not in yesterday_heatmap.columns:
        return {name: "NEW" for name in today_ranks}

    yest_col = "theme_score" if "theme_score" in yesterday_heatmap.columns else yesterday_heatmap.columns[0]
    tv_col = "total_trading_value" if "total_trading_value" in yesterday_heatmap.columns else None
    sort_cols = [yest_col] + ([tv_col] if tv_col else [])
    yesterday_ranked = (
        yesterday_heatmap.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        .head(sector_limit)
        .reset_index(drop=True)
    )
    yesterday_ranks = {str(row["theme_name"]): i + 1 for i, row in yesterday_ranked.iterrows()}

    result: dict[str, str] = {}
    for name, today_rank in today_ranks.items():
        if name not in yesterday_ranks:
            result[name] = "NEW"
        else:
            diff = yesterday_ranks[name] - today_rank
            if diff > 0:
                result[name] = f"▲{diff}"
            elif diff < 0:
                result[name] = f"▼{abs(diff)}"
            else:
                result[name] = "="
    return result
