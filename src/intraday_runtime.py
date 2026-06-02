"""장중 실시간 수집 런타임.

IntradaySnapshotService 를 보유하고 백그라운드 스레드에서 raw message 를 ingest 해
thread-safe 하게 snapshot dict 를 갱신한다.

사용 예 (mock)::

    from src.intraday_snapshot_service import IntradaySnapshotService
    from src.intraday_runtime import IntradayRuntime, make_mock_source

    service = IntradaySnapshotService(sector_map={"000660": ["반도체"]})
    runtime = IntradayRuntime(
        service=service,
        message_source_factory=make_mock_source(["000660"], "sor"),
        snapshot_interval=1.0,
    )
    runtime.start()
    snap = runtime.get_latest_snapshot()   # thread-safe dict or None
    runtime.stop()

사용 예 (WebSocket)::

    async def ws_source():
        async with client:
            async for msg in client.iter_raw_messages(codes, listen_seconds=300):
                if msg.raw and '\"trnm\": \"REAL\"' in msg.raw:
                    yield msg.raw

    runtime = IntradayRuntime(service, lambda: ws_source())
    runtime.start()
"""
from __future__ import annotations

import asyncio
import json
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .intraday_snapshot_service import IntradaySnapshotService
from .intraday_snapshot_serialization import snapshot_to_dict


# ---------------------------------------------------------------------------
# 상태 상수
# ---------------------------------------------------------------------------

RUNTIME_IDLE = "idle"
RUNTIME_RUNNING = "running"
RUNTIME_STOPPED = "stopped"
RUNTIME_ERROR = "error"


# ---------------------------------------------------------------------------
# Mock 메시지 소스 (개발/테스트용)
# ---------------------------------------------------------------------------


def make_mock_source(
    base_codes: list[str],
    exchange: str = "sor",
    tick_interval: float = 0.05,
    sector_map: "dict[str, list[str]] | None" = None,
) -> Callable[[], Any]:
    """섹터 레짐 기반 mock REAL 메시지 소스.

    섹터 단위로 A/B/C/cold/bear 레짐을 부여하고 ~60초마다 전환한다.
    각 종목은 자신의 섹터 레짐 목표 등락률로 천천히 수렴하여
    임계값(+5%) 근처의 급격한 진입/탈락을 방지한다.

    Args:
        base_codes:  종목코드 리스트.
        exchange:    exchange 종류 (sor / nxt / krx).
        tick_interval: 배치당 대기 시간(초). 기본 0.05초.
        sector_map:  code → sectors 역방향 매핑.
                     전달하면 섹터 단위 레짐을 사용하고,
                     없으면 개별 종목 레짐으로 fallback한다.
    """
    from .kiwoom_websocket import format_kiwoom_code

    # 레짐별 목표 등락률 범위 (center, half_spread)
    # strong_riser_count(10%↑) 기준으로 A/B/C 등급이 결정되므로
    # 각 레짐의 분포가 등급 경계(5%, 10%)로부터 충분히 떨어져야 함
    _REGIME: dict[str, tuple[float, float]] = {
        "A":    (13.0, 2.5),   # 10.5 ~ 15.5% → 대부분 10%↑ → A급
        "B":    (9.0,  2.0),   # 7.0  ~ 11.0% → 1~2종목 10%↑ → B급
        "C":    (6.2,  0.8),   # 5.4  ~  7.0% → 10%↑ 없음, 5%↑ 다수 → C급
        "cold": (-1.5, 2.5),   # -4.0 ~  1.0% → 5%↑ 3개 미만 → threshold 미달
        "bear": (-6.0, 2.5),   # -8.5 ~ -3.5% → 급락
    }
    # 레짐 전환 가중치 (from → {to: weight})
    # A→cold/bear 직접 점프 금지: 반드시 B→C→cold 순차 경로만 허용
    _TRANSITIONS: dict[str, dict[str, float]] = {
        "A":    {"A": 0.50, "B": 0.50, "C": 0.00, "cold": 0.00, "bear": 0.00},
        "B":    {"A": 0.25, "B": 0.35, "C": 0.30, "cold": 0.10, "bear": 0.00},
        "C":    {"A": 0.05, "B": 0.20, "C": 0.30, "cold": 0.35, "bear": 0.10},
        "cold": {"A": 0.05, "B": 0.10, "C": 0.20, "cold": 0.45, "bear": 0.20},
        "bear": {"A": 0.00, "B": 0.05, "C": 0.10, "cold": 0.35, "bear": 0.50},
    }
    # 레짐 전환 간격: 데모 20초 (실전은 60초 권장)
    _REGIME_CHANGE_BATCHES = max(1, int(20.0 / tick_interval))

    def _pick_regime(from_regime: str) -> str:
        pool = _TRANSITIONS[from_regime]
        keys, weights = list(pool.keys()), list(pool.values())
        return random.choices(keys, weights=weights, k=1)[0]

    def _target_for_regime(regime: str) -> float:
        c, s = _REGIME[regime]
        return round(random.uniform(c - s, c + s), 2)

    def _factory() -> Any:
        async def _gen():
            # ── 섹터별 역방향 인덱스 구성 ──────────────────────
            code_to_sector: dict[str, str] = {}
            sector_to_codes: dict[str, list[str]] = {}
            if sector_map:
                for code in base_codes:
                    sectors_list = sector_map.get(code, [])
                    if sectors_list:
                        s = sectors_list[0]
                        code_to_sector[code] = s
                        sector_to_codes.setdefault(s, []).append(code)

            # ── 초기 섹터 레짐 배정 (shuffle → 종목 수와 무관하게 분산) ──
            qualifying = [s for s, codes in sector_to_codes.items() if len(codes) >= 3]
            random.shuffle(qualifying)  # 종목 많은 섹터가 A를 독점하지 않도록
            n_q = len(qualifying)
            sector_regime: dict[str, str] = {}
            sector_countdown: dict[str, int] = {}

            for i, s in enumerate(qualifying):
                if i < n_q * 0.13:      # ~13% A급
                    regime = "A"
                elif i < n_q * 0.35:    # ~22% B급
                    regime = "B"
                elif i < n_q * 0.57:    # ~22% C급
                    regime = "C"
                elif i < n_q * 0.80:    # ~23% cold
                    regime = "cold"
                else:                   # ~20% bear
                    regime = "bear"
                sector_regime[s] = regime
                # 전환 시점을 분산
                sector_countdown[s] = _REGIME_CHANGE_BATCHES + random.randint(
                    -_REGIME_CHANGE_BATCHES // 3, _REGIME_CHANGE_BATCHES // 3
                )

            # sector_map 없거나 섹터 코드 <3인 종목은 개별 cold/bear 레짐
            def _initial_regime_for_code(code: str) -> str:
                s = code_to_sector.get(code)
                if s and s in sector_regime:
                    return sector_regime[s]
                return random.choice(["cold", "cold", "bear"])

            # ── 종목별 초기 상태 ───────────────────────────────
            code_state: dict[str, dict] = {}
            for code in base_codes:
                regime = _initial_regime_for_code(code)
                target = _target_for_regime(regime)
                code_state[code] = {
                    "price": random.randint(10_000, 200_000),
                    "acc_tv": random.randint(1_000_000_000, 10_000_000_000),
                    "change_rate": target,  # target에서 바로 시작 → 초기 threshold 진동 방지
                    "target": target,
                }

            batch = 0
            while True:
                batch += 1
                now_str = datetime.now().strftime("%H%M%S")

                # ── 섹터 레짐 전환 체크 ────────────────────────
                for s in list(sector_countdown.keys()):
                    sector_countdown[s] -= 1
                    if sector_countdown[s] <= 0:
                        new_regime = _pick_regime(sector_regime[s])
                        sector_regime[s] = new_regime
                        sector_countdown[s] = _REGIME_CHANGE_BATCHES + random.randint(
                            -_REGIME_CHANGE_BATCHES // 3, _REGIME_CHANGE_BATCHES // 3
                        )
                        # 해당 섹터 코드의 목표 등락률 갱신
                        for code in sector_to_codes.get(s, []):
                            code_state[code]["target"] = _target_for_regime(new_regime)

                # ── 종목별 tick 생성 ───────────────────────────
                for code in base_codes:
                    st = code_state[code]
                    # 목표 등락률로 천천히 수렴 + 소량 노이즈
                    gap = st["target"] - st["change_rate"]
                    drift = gap * 0.012 + random.gauss(0, 0.12)
                    drift = max(-0.4, min(0.4, drift))
                    st["change_rate"] = round(st["change_rate"] + drift, 2)
                    price_delta = drift / 10.0
                    st["price"] = max(100, int(st["price"] * (1 + price_delta / 100)))
                    st["acc_tv"] += random.randint(50_000_000, 500_000_000)

                    item = format_kiwoom_code(code, exchange)
                    p = st["price"]
                    cr = st["change_rate"]
                    yield json.dumps({
                        "trnm": "REAL",
                        "data": [{
                            "item": item, "type": "0B", "name": "주식체결",
                            "10": f"+{p}" if p >= 0 else str(p),
                            "12": f"+{cr:.2f}" if cr >= 0 else f"{cr:.2f}",
                            "15": "+100", "13": "+1000000",
                            "14": f"+{st['acc_tv']}", "20": now_str,
                        }],
                    })
                await asyncio.sleep(tick_interval)

        return _gen()

    return _factory


# ---------------------------------------------------------------------------
# WebSocket 메시지 소스 (운영용)
# ---------------------------------------------------------------------------


def make_websocket_source(
    base_codes: list[str],
    exchange: str = "sor",
    listen_seconds: float = 7200,
) -> Callable[[], Any]:
    """Kiwoom WebSocket SOR/NXT/KRX 실전 시세를 수신하는 async source factory.

    os.environ["KIWOOM_ENV"] 가 설정되어 있어야 한다.
    ("prod" 또는 "real" 이면 실전 키 사용, "mock" 이면 모의투자 키 사용.)

    Args:
        base_codes:     종목코드 리스트 (6자리).
        exchange:       "sor" | "nxt" | "krx". 기본 "sor".
        listen_seconds: WebSocket 수신 시간(초). 기본 7200(2시간).

    Returns:
        호출하면 async generator 를 반환하는 callable.

    Raises:
        RuntimeError: Kiwoom 설정 로드 실패 시.
    """

    def _factory() -> Any:
        async def _gen():
            from .kiwoom_auth import KiwoomAuthError, issue_access_token, load_kiwoom_api_config
            from .kiwoom_websocket import KiwoomWebSocketClient, format_kiwoom_code

            try:
                config = load_kiwoom_api_config()
            except KiwoomAuthError as exc:
                raise RuntimeError(f"Kiwoom 설정 오류: {exc}") from exc

            token = issue_access_token(
                config.rest_host, config.app_key, config.secret_key, timeout=15.0
            )

            formatted = [format_kiwoom_code(c, exchange) for c in base_codes]
            reg_groups = [
                (str(i + 1), formatted[s: s + 200])
                for i, s in enumerate(range(0, len(formatted), 200))
            ]

            client = KiwoomWebSocketClient(config.ws_url, token, connect_timeout=15.0)
            async with client:
                async for msg in client.iter_raw_messages(
                    formatted,
                    listen_seconds=listen_seconds,
                    include_control_messages=False,
                    reg_groups=reg_groups,
                ):
                    if msg.raw:
                        yield msg.raw

        return _gen()

    return _factory


# ---------------------------------------------------------------------------
# IntradayRuntime
# ---------------------------------------------------------------------------


class IntradayRuntime:
    """장중 실시간 수집 런타임.

    백그라운드 스레드에서 asyncio 이벤트 루프를 실행하고,
    message_source_factory 가 반환하는 iterable 에서 raw 메시지를 수신해
    IntradaySnapshotService 에 ingest 한다.

    snapshot_interval 마다 service.get_snapshot() 을 호출해 최신 snapshot dict
    를 thread-safe 하게 저장한다.
    """

    def __init__(
        self,
        service: IntradaySnapshotService,
        message_source_factory: Callable[[], Any],
        snapshot_interval: float = 1.0,
    ) -> None:
        """
        Args:
            service:                IntradaySnapshotService 인스턴스.
            message_source_factory: 호출 시 raw 메시지 iterable 을 반환하는 callable.
                                    async iterable (권장) 또는 sync iterable 모두 가능.
            snapshot_interval:      snapshot 갱신 주기(초). 기본 1.0 초.
        """
        self._service = service
        self._message_source_factory = message_source_factory
        self._snapshot_interval = snapshot_interval

        # 스레드 세이프 상태
        self._lock = threading.Lock()
        self._latest_snapshot: dict | None = None
        self._state: str = RUNTIME_IDLE
        self._error: str | None = None
        self._close_reason: str | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None

        # 스레딩
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """백그라운드 수집 스레드를 시작한다. 이미 실행 중이면 no-op."""
        with self._lock:
            if self._state == RUNTIME_RUNNING:
                return
            self._state = RUNTIME_RUNNING
            self._error = None
            self._close_reason = None
            self._started_at = datetime.now()
            self._stopped_at = None

        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            daemon=True,
            name="IntradayRuntime",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """수집 스레드에 종료를 요청하고 최대 timeout 초 대기한다."""
        self._stop_requested.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def wait(self, timeout: float = 5.0) -> None:
        """stop 요청 없이 스레드가 자연 종료될 때까지 최대 timeout 초 대기한다.

        소스가 스스로 소진되거나 예외로 종료되기를 기다릴 때 사용한다.
        테스트에서 close_reason / error 상태를 검증할 때 유용하다.
        """
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        """수집 스레드가 실행 중이면 True."""
        with self._lock:
            return self._state == RUNTIME_RUNNING

    def get_latest_snapshot(self) -> dict | None:
        """thread-safe 하게 최신 snapshot dict 를 반환한다.

        아직 snapshot 이 계산되지 않았으면 None 을 반환한다.
        """
        with self._lock:
            return self._latest_snapshot

    def get_status(self) -> dict:
        """런타임 상태 요약을 thread-safe dict 로 반환한다."""
        with self._lock:
            return {
                "state": self._state,
                "error": self._error,
                "close_reason": self._close_reason,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            }

    # ------------------------------------------------------------------
    # 내부 스레드 / async 루프
    # ------------------------------------------------------------------

    def _thread_main(self) -> None:
        """백그라운드 스레드 진입점. 자체 asyncio 이벤트 루프를 실행한다."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_loop())
        except Exception as exc:
            with self._lock:
                self._state = RUNTIME_ERROR
                self._error = str(exc)
                self._stopped_at = datetime.now()
        finally:
            loop.close()

    async def _async_loop(self) -> None:
        """메시지를 ingest 하고 주기적으로 snapshot 을 갱신한다."""
        last_snap = time.monotonic()

        try:
            source = self._message_source_factory()
            async for raw in self._guarded_iter(source):
                # stop 요청 확인 — 소스 exception 전파보다 우선순위 낮음
                if self._stop_requested.is_set():
                    break

                try:
                    self._service.ingest_raw_message(raw)
                except Exception:
                    pass  # 단일 메시지 오류로 전체가 중단되지 않도록

                now = time.monotonic()
                if now - last_snap >= self._snapshot_interval:
                    self._refresh_snapshot()
                    last_snap = now

        except Exception as exc:
            cause = str(exc)
            with self._lock:
                # 1000 OK Bye 는 정상 종료 → close_reason 에 기록
                if "1000" in cause and ("Bye" in cause or "OK" in cause):
                    self._close_reason = cause
                else:
                    self._error = cause

        finally:
            self._refresh_snapshot()
            with self._lock:
                if self._state == RUNTIME_RUNNING:
                    self._state = RUNTIME_STOPPED
                self._stopped_at = datetime.now()

    async def _guarded_iter(self, source: Any):
        """source(async 또는 sync iterable)를 투명하게 wrap 한다.

        소스에서 발생하는 예외가 _async_loop 의 except 블록으로 자연스럽게 전파되도록
        이 함수 안에서 stop 체크를 하지 않는다.
        stop 체크는 _async_loop 에서 메시지 수신 직후에 수행한다.
        """
        if hasattr(source, "__aiter__"):
            async for item in source:
                yield item
        else:
            for item in source:
                yield item
                await asyncio.sleep(0)  # event loop 에 제어 반환

    def _refresh_snapshot(self) -> None:
        """service 에서 snapshot 을 계산해 thread-safe 하게 저장한다."""
        try:
            snap = self._service.get_snapshot()
            snap_dict = snapshot_to_dict(snap)
            with self._lock:
                self._latest_snapshot = snap_dict
        except Exception:
            pass
