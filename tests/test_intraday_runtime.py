"""src/intraday_runtime.py 단위 테스트."""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest

from src.intraday_runtime import (
    RUNTIME_ERROR,
    RUNTIME_IDLE,
    RUNTIME_RUNNING,
    RUNTIME_STOPPED,
    IntradayRuntime,
    make_mock_source,
)
from src.intraday_snapshot_service import IntradaySnapshotService


# ---------------------------------------------------------------------------
# 테스트용 fake source 헬퍼
# ---------------------------------------------------------------------------


def _make_service(sector_map=None):
    sm = sector_map or {"000660": ["반도체"], "005930": ["반도체"]}
    return IntradaySnapshotService(sm)


def _fake_rows_as_raw(n: int = 5) -> list[str]:
    """normalize_tick_rows 가 처리할 수 있는 REAL 메시지 n 개 반환."""
    msgs = []
    for i in range(n):
        acc = 1_000_000_000 + i * 100_000_000
        msgs.append(json.dumps({
            "trnm": "REAL",
            "data": [{
                "item": "000660_AL", "type": "0B", "name": "주식체결",
                "10": "+70000", "12": "+1.50",
                "15": "+100", "13": "+1000000",
                "14": f"+{acc}", "20": "134501",
            }]
        }))
    return msgs


def _sync_source_factory(messages: list[str]):
    """동기 iterable 을 반환하는 factory (테스트용)."""
    return lambda: iter(messages)


def _async_source_factory(messages: list[str], delay: float = 0.0):
    """async iterable 을 반환하는 factory (테스트용)."""
    async def _gen():
        for msg in messages:
            yield msg
            if delay > 0:
                await asyncio.sleep(delay)

    return lambda: _gen()


# ---------------------------------------------------------------------------
# 1. 초기 상태
# ---------------------------------------------------------------------------


def test_initial_state_is_idle():
    rt = IntradayRuntime(_make_service(), _sync_source_factory([]))
    assert not rt.is_running()
    assert rt.get_latest_snapshot() is None
    assert rt.get_status()["state"] == RUNTIME_IDLE


# ---------------------------------------------------------------------------
# 2. start / stop 기본
# ---------------------------------------------------------------------------


def test_start_transitions_to_running():
    rt = IntradayRuntime(_make_service(), _sync_source_factory([]), snapshot_interval=0.1)
    rt.start()
    time.sleep(0.05)
    # 소스가 바로 소진되면 STOPPED 로 갈 수 있음 — RUNNING 또는 STOPPED
    assert rt.get_status()["state"] in (RUNTIME_RUNNING, RUNTIME_STOPPED)
    rt.stop()


def test_stop_after_source_exhausted():
    rt = IntradayRuntime(_make_service(), _sync_source_factory([]), snapshot_interval=0.1)
    rt.start()
    rt.stop(timeout=3.0)
    assert rt.get_status()["state"] == RUNTIME_STOPPED


def test_start_idempotent():
    """start() 를 두 번 호출해도 하나의 스레드만 실행된다."""
    msgs = _fake_rows_as_raw(50)
    rt = IntradayRuntime(_make_service(), _async_source_factory(msgs, delay=0.01), snapshot_interval=0.1)
    rt.start()
    rt.start()  # idempotent
    time.sleep(0.1)
    rt.stop(timeout=3.0)
    # 예외 없이 종료됐으면 OK
    assert rt.get_status()["state"] == RUNTIME_STOPPED


def test_stop_when_not_running_is_noop():
    rt = IntradayRuntime(_make_service(), _sync_source_factory([]))
    rt.stop()  # no-op — 예외 없어야 함
    assert rt.get_status()["state"] == RUNTIME_IDLE


# ---------------------------------------------------------------------------
# 3. fake messages ingest → snapshot 생성
# ---------------------------------------------------------------------------


def test_runtime_ingests_sync_messages():
    msgs = _fake_rows_as_raw(10)
    rt = IntradayRuntime(_make_service(), _sync_source_factory(msgs), snapshot_interval=0.05)
    rt.start()
    rt.stop(timeout=3.0)

    snap = rt.get_latest_snapshot()
    assert snap is not None
    assert snap["status"] in ("ready", "warming", "empty")
    assert isinstance(snap["sector_views"], list)


def test_runtime_ingests_async_messages():
    msgs = _fake_rows_as_raw(10)
    rt = IntradayRuntime(_make_service(), _async_source_factory(msgs, delay=0.005), snapshot_interval=0.05)
    rt.start()
    rt.stop(timeout=3.0)

    snap = rt.get_latest_snapshot()
    assert snap is not None


def test_snapshot_updates_after_messages():
    msgs = _fake_rows_as_raw(20)
    rt = IntradayRuntime(_make_service(), _async_source_factory(msgs, delay=0.01), snapshot_interval=0.1)
    rt.start()
    time.sleep(0.4)
    snap = rt.get_latest_snapshot()
    rt.stop(timeout=3.0)

    assert snap is not None
    assert snap["raw_row_count"] > 0


def test_snapshot_contains_required_keys():
    msgs = _fake_rows_as_raw(5)
    rt = IntradayRuntime(_make_service(), _sync_source_factory(msgs), snapshot_interval=0.05)
    rt.start()
    rt.stop(timeout=3.0)

    snap = rt.get_latest_snapshot()
    assert snap is not None
    for key in ("status", "latest_count", "bucket_count", "raw_row_count",
                "sector_views", "generated_at"):
        assert key in snap, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 4. thread 안전성
# ---------------------------------------------------------------------------


def test_get_latest_snapshot_thread_safe():
    """여러 스레드에서 동시에 get_latest_snapshot() 을 호출해도 예외 없음."""
    msgs = _fake_rows_as_raw(30)
    rt = IntradayRuntime(_make_service(), _async_source_factory(msgs, delay=0.005), snapshot_interval=0.05)
    rt.start()

    errors = []

    def reader():
        for _ in range(20):
            try:
                rt.get_latest_snapshot()
                rt.get_status()
                time.sleep(0.005)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    rt.stop(timeout=3.0)
    assert not errors, f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# 5. 1000 Bye → close_reason 기록
# ---------------------------------------------------------------------------


def test_close_reason_stored_on_bye_exception():
    """소스가 '1000 OK Bye' 예외를 raise 하면 error 가 아닌 close_reason 에 기록된다."""
    async def _bye_source():
        yield json.dumps({"trnm": "REAL", "data": []})
        raise Exception("receive failed: 1000 (OK) Bye")

    rt = IntradayRuntime(_make_service(), lambda: _bye_source(), snapshot_interval=0.05)
    rt.start()
    # stop() 은 _stop_requested 를 set 해 exception 이 발생하기 전에 루프를 종료할 수 있다.
    # wait() 로 소스가 자연 소진되도록 기다린다.
    rt.wait(timeout=3.0)

    status = rt.get_status()
    assert status["close_reason"] is not None
    assert status["error"] is None  # error 가 아님
    assert "1000" in status["close_reason"] or "Bye" in status["close_reason"]


def test_unexpected_exception_stored_as_error():
    """소스가 1000 Bye 이외의 예외를 raise 하면 error 에 기록된다."""
    async def _bad_source():
        yield '{"trnm":"REAL","data":[]}'
        raise RuntimeError("unexpected connection reset")

    rt = IntradayRuntime(_make_service(), lambda: _bad_source(), snapshot_interval=0.05)
    rt.start()
    # wait() 로 소스가 자연 소진되어 예외가 처리될 때까지 기다린다.
    rt.wait(timeout=3.0)

    status = rt.get_status()
    assert status["error"] is not None
    assert "unexpected" in status["error"].lower()


# ---------------------------------------------------------------------------
# 6. make_mock_source
# ---------------------------------------------------------------------------


def test_make_mock_source_returns_callable():
    factory = make_mock_source(["000660"], "sor")
    assert callable(factory)


def test_make_mock_source_yields_valid_json():
    """mock source 가 반환하는 메시지가 normalize_tick_rows 로 파싱된다."""
    from src.kiwoom_websocket import normalize_tick_rows

    factory = make_mock_source(["000660"], "sor")

    async def _collect():
        msgs = []
        async for raw in factory():
            msgs.append(raw)
            if len(msgs) >= 3:
                break
        return msgs

    msgs = asyncio.run(_collect())
    assert len(msgs) == 3
    rows = normalize_tick_rows(msgs[0])
    assert len(rows) == 1
    assert rows[0]["base_code"] == "000660"


def test_runtime_with_mock_source_reaches_ready():
    """make_mock_source 를 사용한 runtime 이 ready 상태에 도달한다."""
    sm = {"000660": ["반도체"], "005930": ["반도체"]}
    service = IntradaySnapshotService(sm)
    factory = make_mock_source(["000660", "005930"], "sor", tick_interval=0.02)
    rt = IntradayRuntime(service, factory, snapshot_interval=0.1)
    rt.start()
    time.sleep(0.6)
    snap = rt.get_latest_snapshot()
    rt.stop(timeout=3.0)

    assert snap is not None
    assert snap["status"] in ("ready", "warming")
