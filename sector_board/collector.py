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
    _log.info("[sector-board] calling get_morning_board_view_models(trade_date=%s)", today)
    summary, heatmap, leaders = get_morning_board_view_models(trade_date=today)
    _log.info("[sector-board] got summary=%s themes=%d leaders=%d",
              summary.get("data_mode"), len(heatmap), len(leaders))
    payload = build_morning_snapshot_payload(summary, heatmap, leaders, generated_at=datetime.now())
    payload["snapshot_date"] = today.isoformat()

    # 상승이유 분석 (Naver 뉴스 + OpenAI 요약 — 실패해도 수집은 계속)
    try:
        from src.evidence_service import build_evidence_bundles
        from src.rise_reason_service import summarize_rise_reasons
        _log.info("[sector-board] building evidence bundles (limit=20)...")
        evidence_bundles = build_evidence_bundles(limit=10)
        payload["rise_reasons"] = summarize_rise_reasons(evidence_bundles)
        _log.info("[sector-board] rise_reasons collected: %d", len(payload["rise_reasons"]))
    except Exception as exc:
        _log.warning("[sector-board] rise_reason collection skipped (non-fatal): %s", exc)
        payload["rise_reasons"] = []

    result = upsert_snapshot(payload, database_url=database_url, auto_create=True)
    _log.info("[sector-board] upsert done: %s", result)
    return result


def collect_intraday_and_store(
    database_url: str,
    snapshot_date: date | None = None,
) -> dict[str, Any]:
    """Collect an intraday V1 snapshot and persist by overwriting today's row."""
    try:
        from src.config import load_settings
        settings = load_settings()
        if not settings.intraday_board_enabled:
            _log.info("[sector-board] intraday disabled; using morning collector")
            return collect_and_store(database_url, snapshot_date=snapshot_date)

        from src.market_data import get_intraday_board_view_models
        from .repository import fetch_snapshot, upsert_snapshot

        today = snapshot_date or date.today()
        previous_snapshot = None
        try:
            previous_snapshot = fetch_snapshot(database_url=database_url, snapshot_date=today)
        except Exception as exc:
            _log.warning("[sector-board] previous intraday snapshot unavailable: %s", exc)

        payload = get_intraday_board_view_models(previous_snapshot=previous_snapshot)
        payload["snapshot_date"] = today.isoformat()
        payload.setdefault("summary", {})["snapshot_date"] = today.isoformat()
        _attach_intraday_evidence(payload, settings, trade_date=today)
        result = upsert_snapshot(payload, database_url=database_url, auto_create=True)
        _log.info(
            "[sector-board] intraday upsert done: %s themes=%d leaders=%d",
            result,
            len(payload.get("themes", [])),
            len(payload.get("leaders", [])),
        )
        return result
    except Exception as exc:
        _log.error("[sector-board] intraday collect failed; falling back to morning collector: %s", exc)
        return collect_and_store(database_url, snapshot_date=snapshot_date)


def _attach_intraday_evidence(payload: dict[str, Any], settings: Any, trade_date: date) -> None:
    summary = payload.setdefault("summary", {})
    if not getattr(settings, "intraday_evidence_enabled", False):
        summary["evidence_status"] = {
            "enabled": False,
            "status": "disabled",
            "message": "INTRADAY_EVIDENCE_ENABLED=false",
        }
        return

    limit = int(getattr(settings, "intraday_evidence_limit", 10) or 0)
    try:
        from src.evidence_service import build_evidence_bundles_for_leaders
        from src.rise_reason_service import summarize_rise_reasons

        bundles = build_evidence_bundles_for_leaders(
            payload.get("leaders", []),
            limit=limit,
            trade_date=trade_date,
        )
        if not bundles:
            payload["rise_reasons"] = []
            summary["evidence_status"] = {
                "enabled": True,
                "status": "empty",
                "message": "No evidence bundles were created for intraday leaders.",
                "count": 0,
            }
            return

        payload["rise_reasons"] = summarize_rise_reasons(bundles)
        summary["evidence_status"] = {
            "enabled": True,
            "status": "ok",
            "message": "Intraday leader evidence collected.",
            "bundle_count": len(bundles),
            "count": len(payload["rise_reasons"]),
        }
    except Exception as exc:
        _log.warning("[sector-board] intraday evidence skipped (non-fatal): %s", exc)
        payload["rise_reasons"] = []
        summary["evidence_status"] = {
            "enabled": True,
            "status": "error",
            "message": str(exc),
            "count": 0,
        }


def _intraday_board_enabled() -> bool:
    try:
        from src.config import load_settings
        return bool(load_settings().intraday_board_enabled)
    except Exception:
        return False


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
            if _intraday_board_enabled():
                result = collect_intraday_and_store(database_url, snapshot_date=today)
            else:
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
