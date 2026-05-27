from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

_log = logging.getLogger(__name__)

_scheduler = None
_scheduler_lock = threading.Lock()


def _collect_job(database_url: str) -> None:
    """매일 04:00 KST에 실행: 전 거래일 전체 KRX 데이터 수집."""
    try:
        from src.krx_collector import get_last_trading_date
        target_date = get_last_trading_date()
    except Exception as exc:
        _log.warning("[scheduler] get_last_trading_date 실패, 어제 날짜 사용: %s", exc)
        target_date = date.today() - timedelta(days=1)

    _log.info("[scheduler] 일일 수집 시작: trade_date=%s", target_date)
    try:
        from .collector import collect_and_store
        result = collect_and_store(database_url, snapshot_date=target_date)
        _log.info("[scheduler] 수집 완료: %s", result)
    except Exception as exc:
        _log.error("[scheduler] 수집 실패: %s", exc)


def trigger_startup_collect_if_needed(database_url: str) -> None:
    """앱 시작 시 최신 스냅샷이 없거나 오래됐으면 백그라운드 수집 즉시 시작."""
    try:
        from .repository import fetch_snapshot
        from src.krx_collector import get_last_trading_date

        snapshot = fetch_snapshot(database_url=database_url)
        last_trade = get_last_trading_date()
        snapshot_date_str = snapshot.get("snapshot_date") if snapshot else None
        refresh_status = snapshot.get("refresh_status") if snapshot else None

        needs_collect = (
            snapshot is None
            or snapshot_date_str != last_trade.isoformat()
            or refresh_status == "error"
        )
        if needs_collect:
            _log.info(
                "[scheduler] 시작 시 수집 필요 (DB=%s, 전거래일=%s) — 백그라운드 즉시 실행",
                snapshot_date_str, last_trade,
            )
            threading.Thread(
                target=_collect_job,
                args=(database_url,),
                daemon=True,
                name="sector-board-startup-collect",
            ).start()
        else:
            _log.info("[scheduler] 최신 스냅샷 확인됨 (%s) — 즉시 수집 불필요", snapshot_date_str)
    except Exception as exc:
        _log.warning("[scheduler] 시작 시 수집 확인 실패 (무시): %s", exc)


def setup_daily_scheduler(database_url: str, collect_hour: int = 4) -> None:
    """매일 collect_hour:00 KST에 전 거래일 전체 KRX 수집 스케줄 등록.

    apscheduler 또는 pytz 미설치 시 조용히 건너뜀 (기능 저하, 오류 없음).
    """
    global _scheduler

    if _scheduler is not None:
        return

    with _scheduler_lock:
        if _scheduler is not None:
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            import pytz
        except ImportError:
            _log.warning("[scheduler] apscheduler / pytz 미설치 — 일일 스케줄러 비활성")
            return

        kst = pytz.timezone("Asia/Seoul")
        sched = BackgroundScheduler(timezone=kst)
        sched.add_job(
            _collect_job,
            CronTrigger(hour=collect_hour, minute=0, timezone=kst),
            args=[database_url],
            id="sector_board_daily_collect",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        sched.start()
        _scheduler = sched
        _log.info("[scheduler] 일일 수집 등록: 매일 %02d:00 KST", collect_hour)
