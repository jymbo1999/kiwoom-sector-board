from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import Any

_log = logging.getLogger(__name__)
_collect_lock = threading.Lock()


def collect_and_store(
    database_url: str,
    snapshot_date: date | None = None,
) -> dict[str, Any]:
    """Collect Kiwoom data and persist to DB. Raises on failure."""
    import sys
    _log.info("[sector-board] Python %s | site-packages: %s", sys.version.split()[0],
              next((p for p in sys.path if "site-packages" in p), "?"))

    try:
        from src.market_data import get_morning_board_view_models
        _log.info("[sector-board] src.market_data imported OK")
    except ImportError as exc:
        import traceback
        _log.error("[sector-board] src.market_data import FAILED:\n%s", traceback.format_exc())
        raise

    try:
        from src.snapshot_service import build_morning_snapshot_payload
    except ImportError as exc:
        _log.error("[sector-board] src.snapshot_service import FAILED: %s", exc)
        raise

    from .repository import upsert_snapshot

    today = snapshot_date or date.today()
    _log.info("[sector-board] calling get_morning_board_view_models()")
    summary, heatmap, leaders = get_morning_board_view_models()
    _log.info("[sector-board] got summary=%s themes=%d leaders=%d",
              summary.get("data_mode"), len(heatmap), len(leaders))
    payload = build_morning_snapshot_payload(summary, heatmap, leaders, generated_at=datetime.now())
    payload["snapshot_date"] = today.isoformat()
    result = upsert_snapshot(payload, database_url=database_url, auto_create=True)
    _log.info("[sector-board] upsert done: %s", result)
    return result


def schedule_background_collect(
    database_url: str,
    snapshot_date: date | None = None,
) -> bool:
    """Start a background Kiwoom data collection thread.

    Returns True if collection was started, False if already in progress.
    """
    from .repository import set_refresh_error, set_refresh_running

    today = snapshot_date or date.today()

    if not _collect_lock.acquire(blocking=False):
        _log.info("[sector-board] collect skipped: already running (in-process lock)")
        return False

    try:
        set_refresh_running(database_url=database_url, snapshot_date=today)
    except Exception as exc:
        _log.error("[sector-board] set_refresh_running failed: %s", exc)
        _collect_lock.release()
        return False

    def _run() -> None:
        try:
            result = collect_and_store(database_url, snapshot_date=today)
            _log.info("[sector-board] collect completed: %s", result)
        except Exception as exc:
            _log.error("[sector-board] collect failed: %s", exc)
            try:
                set_refresh_error(
                    database_url=database_url,
                    snapshot_date=today,
                    error=str(exc),
                )
            except Exception:
                pass
        finally:
            _collect_lock.release()

    threading.Thread(target=_run, daemon=True, name="sector-board-collect").start()
    return True
