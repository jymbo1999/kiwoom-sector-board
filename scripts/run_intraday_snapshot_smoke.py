"""장중 실시간 Snapshot Smoke Script.

IntradaySnapshotService에 Kiwoom WebSocket REAL message를 공급하고
일정 주기마다 콘솔에 장중 주도섹터/대장주 랭킹을 출력한다.

Flask/DB 연결 없는 순수 콘솔 검증 단계.

사용 예::

    # mock (로컬 확인, API 키 불필요)
    python scripts/run_intraday_snapshot_smoke.py \\
      --provider mock --exchange sor \\
      --codes 005930,000660,035420,000270,042660 \\
      --listen-seconds 10 --summary-interval-seconds 2

    # prod WebSocket 권장 실행 (실전 키 필요, 장중 08:00~18:00 KST)
    KIWOOM_REAL_APP_KEY=<키> KIWOOM_REAL_SECRET_KEY=<시크릿> \\
    python scripts/run_intraday_snapshot_smoke.py \\
      --provider websocket --kiwoom-env prod --exchange sor \\
      --codes-file data/universe_codes_150.txt \\
      --sector-map-file data/sector_map.json \\
      --listen-seconds 300 --summary-interval-seconds 30 \\
      --dump-snapshot-jsonl

    # 서버 1000 Bye 안내:
    #   "WebSocket 정상 종료 (1000 OK Bye)" 는 LOGIN 실패가 아닙니다.
    #   서버 연결 수명 초과 또는 장 마감 후 서버 정상 종료입니다.
    #   스크립트를 다시 실행하면 재연결됩니다.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import random
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.intraday_snapshot_service import IntradaySnapshot, IntradaySnapshotService
from src.intraday_snapshot_serialization import snapshot_to_dict
from src.kiwoom_websocket import format_kiwoom_code, normalize_tick_rows

_SENSITIVE_KEYS = frozenset({"token", "appkey", "secretkey", "app_key", "secret_key"})

# ---------------------------------------------------------------------------
# Mock price table (smoke test용 참고값)
# ---------------------------------------------------------------------------

_BASE_PRICES: dict[str, int] = {
    "005930": 82000, "000660": 180000, "042700": 117000, "000990": 45000, "011070": 138000,
    "035420": 175000, "035720": 38000, "036570": 195000,
    "005380": 215000, "000270": 110000, "012330": 285000,
    "010140": 11000, "042660": 25000, "329180": 27000,
    "068270": 185000, "207940": 740000, "091990": 15000,
}
_DEFAULT_BASE_PRICE = 50000

# ---------------------------------------------------------------------------
# smoke test용 임시 fallback sector_map
# 운영 전 별도 universe/sector_map 구축 필요
# ---------------------------------------------------------------------------

_FALLBACK_SECTOR_MAP: dict[str, list[str]] = {
    "005930": ["반도체"], "000660": ["반도체"], "042700": ["반도체"],
    "000990": ["반도체"], "011070": ["반도체"],
    "035420": ["인터넷/게임"], "035720": ["인터넷/게임"], "036570": ["인터넷/게임"],
    "005380": ["자동차"], "000270": ["자동차"], "012330": ["자동차"],
    "010140": ["조선"], "042660": ["조선"], "329180": ["조선"],
    "068270": ["바이오"], "207940": ["바이오"], "091990": ["바이오"],
}

# ---------------------------------------------------------------------------
# Code helpers (unit-testable)
# ---------------------------------------------------------------------------


def parse_codes_str(codes_str: str) -> list[str]:
    """콤마 구분 종목코드 문자열 → 6자리 zero-padded 중복 제거 리스트."""
    seen: dict[str, None] = {}
    for raw in codes_str.split(","):
        s = raw.strip()
        if s.isdigit() and 1 <= len(s) <= 6:
            seen[s.zfill(6)] = None
        elif s:
            print(f"[warn] 유효하지 않은 코드: {s!r}")
    return list(seen)


def parse_codes_file(path: Path) -> list[str]:
    """종목코드 파일 → 6자리 zero-padded 중복 제거 리스트. # 주석·빈 줄 무시."""
    seen: dict[str, None] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.isdigit() and 1 <= len(line) <= 6:
            seen[line.zfill(6)] = None
        else:
            print(f"[warn] 유효하지 않은 코드: {raw_line!r}")
    return list(seen)


def apply_max_codes(codes: list[str], max_codes: int) -> list[str]:
    """max_codes=0이면 제한 없음, 양수면 앞에서 max_codes개만 반환한다."""
    return codes if max_codes <= 0 else codes[:max_codes]


def format_codes(base_codes: list[str], exchange: str) -> list[str]:
    """exchange suffix를 붙인 formatted code 리스트를 반환한다."""
    return [format_kiwoom_code(c, exchange) for c in base_codes]


# ---------------------------------------------------------------------------
# Sector map helpers (unit-testable)
# ---------------------------------------------------------------------------


def get_fallback_sector_map() -> dict[str, list[str]]:
    """smoke test용 임시 fallback sector_map을 반환한다.

    운영 전 별도 universe/sector_map 구축 필요.
    """
    return dict(_FALLBACK_SECTOR_MAP)


def load_sector_map_file(path: Path) -> dict[str, list[str]]:
    """JSON 파일에서 sector_map을 로드한다. 경고는 stdout에 출력된다.

    형식: {"000660": ["반도체"], "005930": ["반도체", "대형주"]}

    잘못된 entry (value 가 list 가 아닌 경우 등) 는 경고를 출력하고 건너뛴다.
    파일이 없으면 FileNotFoundError, JSON 오류 또는 형식 오류면 ValueError 를 raise 한다.
    """
    from src.sector_map_loader import SectorMapLoadError, load_sector_map
    try:
        res = load_sector_map(path, strict=False)
    except FileNotFoundError:
        raise FileNotFoundError(f"sector-map-file을 찾을 수 없습니다: {path}")
    except SectorMapLoadError as exc:
        raise ValueError(str(exc)) from exc
    for w in res.warnings:
        print(f"[warn] {w}")
    return res.sector_map


# ---------------------------------------------------------------------------
# Mock message generator (unit-testable)
# ---------------------------------------------------------------------------


def make_mock_real_message(
    base_code: str,
    exchange: str,
    price: int,
    change_rate: float,
    acc_tv: int,
    trade_time: str,
) -> str:
    """normalize_tick_rows()가 처리할 수 있는 mock REAL 메시지 JSON을 반환한다."""
    item = format_kiwoom_code(base_code, exchange)
    p_str = f"+{price}" if price >= 0 else str(price)
    cr_str = f"+{change_rate:.2f}" if change_rate >= 0 else f"{change_rate:.2f}"
    return json.dumps({
        "trnm": "REAL",
        "data": [{
            "item": item, "type": "0B", "name": "주식체결",
            "10": p_str, "12": cr_str,
            "15": "+100", "13": "+1000000",
            "14": f"+{acc_tv}", "20": trade_time,
        }],
    })


# ---------------------------------------------------------------------------
# Output formatters (unit-testable)
# ---------------------------------------------------------------------------


def _fmt_value(v: int | None) -> str:
    if v is None:
        return "N/A"
    if v >= 100_000_000_000:
        return f"{v / 100_000_000_000:.1f}천억"
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v // 10_000}만"
    return str(v)


def format_snapshot_summary(
    snap: IntradaySnapshot,
    *,
    registered_count: int | None = None,
) -> str:
    """IntradaySnapshot을 콘솔 출력용 문자열로 변환한다.

    Args:
        snap:             IntradaySnapshot 객체.
        registered_count: WebSocket 에 등록한 종목 수.
                          지정하면 no-tick 종목 수(= registered - latest)를 표시한다.
    """
    lines: list[str] = []
    now_str = datetime.now().strftime("%H:%M")
    minute_str = snap.minute_key or "--"
    lines.append(f"\n[smoke] ===== {now_str} snapshot =====")

    no_tick_str = ""
    if registered_count is not None:
        no_tick = max(0, registered_count - snap.latest_count)
        no_tick_str = f" no_tick={no_tick}/{registered_count}"

    lines.append(
        f"status={snap.status} minute={minute_str} latest={snap.latest_count}"
        f" unmapped={snap.unmapped_count}"
        f" buckets={snap.bucket_count} sectors={snap.sector_count}"
        f" raw_rows={snap.raw_row_count} ignored={snap.ignored_row_count}"
        + no_tick_str
    )
    if not snap.sector_views:
        if snap.status == "empty":
            lines.append("  (bucket 없음 — 장중 시간대(08:00~18:00 KST) 또는 provider 를 확인하세요)")
        elif snap.status == "warming":
            reason = []
            if snap.unmapped_count > 0 and snap.latest_count > 0:
                mapped = snap.latest_count - snap.unmapped_count
                reason.append(
                    f"tick 수신 {snap.latest_count}종목 중 "
                    f"sector_map 매핑 {mapped}종목 / 미매핑 {snap.unmapped_count}종목"
                )
            reason.append("--sector-map-file 확인 또는 --min-total-trade-value 0 으로 낮춰 확인")
            lines.append("  (sector_views 없음 — " + "; ".join(reason) + ")")
        return "\n".join(lines)
    lines.append("")
    for sv in snap.sector_views:
        avg_rate = f"{sv.average_change_rate:.2f}%" if sv.average_change_rate is not None else "N/A"
        rising = f"{sv.rising_ratio:.2f}" if sv.rising_ratio is not None else "N/A"
        lines.append(
            f"{sv.rank}. {sv.sector_name}"
            f"  score={sv.sector_score:.0f}"
            f"  trade={_fmt_value(sv.total_minute_trade_value)}"
            f"  avg_rate={avg_rate}"
            f"  rising={rising}"
            f"  active={sv.active_stock_count}"
        )
        for ls in sv.leader_stocks:
            badge = f"{ls.display_badge:3s}" if ls.display_badge else f"#{ls.rank} "
            close = str(ls.close_price) if ls.close_price is not None else "N/A"
            rate = f"{ls.last_change_rate:.2f}%" if ls.last_change_rate is not None else "N/A"
            lv = _fmt_value(ls.minute_trade_value_delta)
            lines.append(f"   {badge} {ls.base_code}  close={close}  rate={rate}  1m_tv={lv}")
    return "\n".join(lines)


def format_final_summary(stats: dict) -> str:
    """최종 요약 문자열을 반환한다."""
    lines = ["\n[smoke] ===== FINAL SUMMARY ====="]
    for key in ("total_messages", "total_ingested_rows", "total_snapshots",
                "final_status", "final_sector_count"):
        lines.append(f"  {key}={stats.get(key, 'N/A')}")
    elapsed = stats.get("elapsed_seconds", 0.0)
    rows = stats.get("total_ingested_rows", 0)
    lines.append(f"  elapsed={elapsed:.1f}s")
    if elapsed > 0:
        lines.append(f"  rows_per_sec={rows / elapsed:.1f}")

    snap: IntradaySnapshot | None = stats.get("final_snapshot")
    if snap is not None and snap.sector_count == 0:
        if snap.bucket_count == 0:
            lines += [
                "",
                "  [hint] sector_views 가 없는 원인:",
                "    - bucket 없음: 장중이 아닐 수 있음 (08:00~18:00 KST)",
                "    - sector_map 에 매핑되지 않은 코드만 수신됨",
                "    - min_total_trade_value 가 너무 높음 (0 으로 낮춰 확인)",
            ]
        else:
            unmapped_hint = (
                f"    - sector_map 미매핑 {snap.unmapped_count}종목 "
                f"(tick 수신 {snap.latest_count}종목 중)"
            ) if snap.unmapped_count > 0 else "    - sector_map 에 매핑되지 않은 코드만 수신됨"
            lines += [
                "",
                "  [hint] sector_views 가 없는 원인:",
                unmapped_hint,
                "    - min_total_trade_value 가 너무 높음 (0 으로 낮춰 확인)",
                "    - min_active_stock_count 기준 미달",
            ]

    if stats.get("jsonl_path"):
        lines.append(f"\n  snapshot JSONL → {stats['jsonl_path']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Snapshot serialization (JSONL dump) — src.intraday_snapshot_serialization 에서 import
# ---------------------------------------------------------------------------
# snapshot_to_dict 는 src/intraday_snapshot_serialization.py 에 정의됨 (위에서 import)


def _write_snapshot_jsonl(snap: IntradaySnapshot, f) -> None:
    f.write(json.dumps(snapshot_to_dict(snap), ensure_ascii=False) + "\n")
    f.flush()


# ---------------------------------------------------------------------------
# Provider runners
# ---------------------------------------------------------------------------


async def _run_mock_provider(
    service: IntradaySnapshotService,
    base_codes: list[str],
    exchange: str,
    listen_seconds: float,
    summary_interval: float,
    stats: dict,
    jsonl_file=None,
    verbose: bool = False,
) -> None:
    """mock provider: fake REAL messages를 생성해 service에 ingest한다."""
    code_state: dict[str, dict] = {
        c: {
            "price": _BASE_PRICES.get(c, _DEFAULT_BASE_PRICE),
            "acc_tv": random.randint(1_000_000_000, 10_000_000_000),
            "change_rate": random.uniform(-1.0, 1.0),
        }
        for c in base_codes
    }

    loop = asyncio.get_event_loop()
    start = loop.time()
    deadline = start + listen_seconds
    next_summary = start + summary_interval

    print(f"[smoke] mock provider: {len(base_codes)}종목  listen={listen_seconds}s")

    while loop.time() < deadline:
        now_str = datetime.now().strftime("%H%M%S")
        for c in base_codes:
            st = code_state[c]
            delta = random.uniform(-0.12, 0.12)
            st["price"] = max(100, int(st["price"] * (1 + delta / 100)))
            st["change_rate"] = round(st["change_rate"] + delta * 0.5, 2)
            st["acc_tv"] += random.randint(50_000_000, 300_000_000)
            msg = make_mock_real_message(
                c, exchange, st["price"], st["change_rate"], st["acc_tv"], now_str,
            )
            n = service.ingest_raw_message(msg)
            stats["total_ingested_rows"] += n
            stats["total_messages"] += 1

        if loop.time() >= next_summary:
            snap = service.get_snapshot()
            stats["total_snapshots"] += 1
            stats["final_snapshot"] = snap
            print(format_snapshot_summary(snap, registered_count=stats.get("registered_count")))
            if jsonl_file:
                _write_snapshot_jsonl(snap, jsonl_file)
            next_summary = loop.time() + summary_interval

        await asyncio.sleep(0.05)


async def _run_websocket_provider(
    service: IntradaySnapshotService,
    base_codes: list[str],
    exchange: str,
    listen_seconds: float,
    summary_interval: float,
    stats: dict,
    jsonl_file=None,
    verbose: bool = False,
) -> None:
    """WebSocket provider: Kiwoom 실전 연결로 REAL message를 수신한다."""
    from src.kiwoom_auth import KiwoomAuthError, issue_access_token, load_kiwoom_api_config
    from src.kiwoom_websocket import KiwoomWebSocketClient, KiwoomWebSocketError

    formatted = format_codes(base_codes, exchange)
    reg_groups = [
        (str(i), formatted[s:s + 200])
        for i, s in enumerate(range(0, len(formatted), 200), start=1)
    ]

    try:
        config = load_kiwoom_api_config()
    except KiwoomAuthError as exc:
        print(f"[smoke] config error: {exc}")
        return

    token = issue_access_token(config.rest_host, config.app_key, config.secret_key, timeout=15.0)
    client = KiwoomWebSocketClient(config.ws_url, token, connect_timeout=15.0)

    loop = asyncio.get_event_loop()
    next_summary = loop.time() + summary_interval
    print(f"[smoke] websocket provider: {len(formatted)}종목  listen={listen_seconds}s")

    try:
        async with client:
            async for msg in client.iter_raw_messages(
                formatted,
                listen_seconds=listen_seconds,
                include_control_messages=True,
                reg_groups=reg_groups,
            ):
                parsed = json.loads(msg.raw) if isinstance(msg.raw, str) else {}
                trnm = parsed.get("trnm", "") if isinstance(parsed, dict) else ""

                if trnm in ("LOGIN", "PING", "REG"):
                    if verbose:
                        print(f"[smoke] ctrl: trnm={trnm}")
                    continue

                if trnm == "REAL":
                    n = service.ingest_raw_message(msg.raw)
                    stats["total_ingested_rows"] += n
                    stats["total_messages"] += 1

                if loop.time() >= next_summary:
                    snap = service.get_snapshot()
                    stats["total_snapshots"] += 1
                    stats["final_snapshot"] = snap
                    print(format_snapshot_summary(snap, registered_count=stats.get("registered_count")))
                    if jsonl_file:
                        _write_snapshot_jsonl(snap, jsonl_file)
                    next_summary = loop.time() + summary_interval

    except KiwoomWebSocketError as exc:
        exc_msg = str(exc)
        if "1000 (OK)" in exc_msg or "1000 OK" in exc_msg:
            print(
                "[smoke] WebSocket 정상 종료 (1000 OK Bye) — "
                "서버 연결 수명 초과 또는 장 마감 후 서버 정상 종료.\n"
                "  LOGIN 실패가 아닙니다. 스크립트를 다시 실행하면 재연결됩니다."
            )
        else:
            print(f"[smoke] WebSocket error: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "IntradaySnapshotService 콘솔 smoke script. "
            "Flask/DB 연결 없는 장중 집계 검증용."
        )
    )
    p.add_argument("--kiwoom-env", dest="kiwoom_env", choices=["mock", "prod", "real"])
    p.add_argument("--provider", choices=["mock", "websocket"], default="mock")
    p.add_argument("--exchange", choices=["krx", "nxt", "sor"], default="sor")
    p.add_argument("--codes", default="")
    p.add_argument("--codes-file", dest="codes_file", default="")
    p.add_argument("--max-codes", dest="max_codes", type=int, default=150)
    p.add_argument("--max-total-realtime-codes", dest="max_total_realtime_codes",
                   type=int, default=200)
    p.add_argument("--listen-seconds", dest="listen_seconds", type=float, default=300.0)
    p.add_argument("--summary-interval-seconds", dest="summary_interval",
                   type=float, default=30.0)
    p.add_argument("--sector-map-file", dest="sector_map_file", default="")
    p.add_argument(
        "--allow-fallback-sector-map", dest="allow_fallback_sector_map",
        action="store_true", default=False,
        help=(
            "--sector-map-file 미지정 시 smoke test 용 임시 fallback sector_map 을 사용한다. "
            "운영 환경에서는 반드시 --sector-map-file 을 지정하라."
        ),
    )
    p.add_argument("--sector-limit", dest="sector_limit", type=int, default=5)
    p.add_argument("--stock-limit", dest="stock_limit", type=int, default=5)
    p.add_argument("--min-total-trade-value", dest="min_total_trade_value",
                   type=int, default=0)
    p.add_argument("--min-active-stock-count", dest="min_active_stock_count",
                   type=int, default=1)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=False)
    p.add_argument("--dump-snapshot-jsonl", dest="dump_snapshot_jsonl",
                   nargs="?", const="", default=None,
                   help="snapshot을 JSONL로 저장. 기본 경로: logs/intraday_snapshot_*.jsonl")
    p.add_argument("--verbose", action="store_true", default=False)
    return p.parse_args()


def _default_jsonl_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "logs" / f"intraday_snapshot_{ts}.jsonl"


async def _run() -> int:
    args = _parse_args()

    if args.kiwoom_env:
        os.environ["KIWOOM_ENV"] = args.kiwoom_env

    # ---- Load codes ----
    raw: list[str] = []
    if args.codes:
        raw.extend(parse_codes_str(args.codes))
    if args.codes_file:
        p = Path(args.codes_file)
        if not p.exists():
            print(f"[smoke] error: --codes-file 없음: {p}")
            return 2
        raw.extend(parse_codes_file(p))

    seen: dict[str, None] = {}
    for c in raw:
        seen[c] = None
    base_codes = apply_max_codes(list(seen), args.max_codes)

    if not base_codes:
        print("[smoke] error: 종목코드 없음. --codes 또는 --codes-file 지정 필요.")
        return 2

    formatted = format_codes(base_codes, args.exchange)
    over_limit = len(formatted) > args.max_total_realtime_codes

    # ---- Load sector_map ----
    if args.sector_map_file:
        try:
            sector_map = load_sector_map_file(Path(args.sector_map_file))
        except (FileNotFoundError, ValueError) as exc:
            print(f"[smoke] error: {exc}")
            return 2
    elif args.dry_run or args.allow_fallback_sector_map:
        sector_map = get_fallback_sector_map()
        qualifier = "dry-run" if args.dry_run else "--allow-fallback-sector-map"
        print(
            f"[smoke] WARNING: --sector-map-file 미지정 → fallback sector_map 사용 ({qualifier}). "
            "운영 전 data/sector_map.json 을 생성하고 --sector-map-file 로 지정하세요."
        )
    else:
        print(
            "[smoke] ERROR: --sector-map-file 이 지정되지 않았습니다.\n"
            "  운영 전 data/sector_map.json 을 생성하고 --sector-map-file 로 지정하세요.\n"
            "  smoke test 목적이라면 --allow-fallback-sector-map 플래그를 추가하세요."
        )
        return 2

    # ---- Dry run ----
    if args.dry_run:
        mapped = sum(1 for c in base_codes if c in sector_map)
        print("[smoke] ===== DRY RUN =====")
        print(f"  provider={args.provider}  exchange={args.exchange}")
        print(f"  base_code_count={len(base_codes)}")
        print(f"  formatted_code_count={len(formatted)}")
        print(f"  max_total_realtime_codes={args.max_total_realtime_codes}")
        print(f"  sector_map_total={len(sector_map)}  mapped_codes={mapped}")
        ex = ", ".join(formatted[:5]) + ("..." if len(formatted) > 5 else "")
        print(f"  examples: {ex}")
        if over_limit:
            print(
                f"  [WARNING] {len(formatted)} > {args.max_total_realtime_codes}. "
                "실전 WebSocket 실행 시 차단됩니다."
            )
        return 0

    # ---- Limit check for websocket ----
    if args.provider == "websocket" and over_limit:
        print(
            f"[smoke] ERROR: formatted_code_count={len(formatted)} > "
            f"max_total_realtime_codes={args.max_total_realtime_codes}. "
            f"--max-codes {args.max_total_realtime_codes} 로 줄이거나 "
            "--max-total-realtime-codes를 조정하세요."
        )
        return 2

    # ---- Setup service ----
    service = IntradaySnapshotService(
        sector_map=sector_map,
        sector_limit=args.sector_limit,
        stock_limit=args.stock_limit,
        min_total_trade_value=args.min_total_trade_value,
        min_active_stock_count=args.min_active_stock_count,
    )

    # ---- JSONL ----
    jsonl_path: Path | None = None
    if args.dump_snapshot_jsonl is not None:
        jsonl_path = (
            Path(args.dump_snapshot_jsonl) if args.dump_snapshot_jsonl else _default_jsonl_path()
        )
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[smoke] snapshot JSONL -> {jsonl_path}")

    print("[smoke] ===== startup =====")
    print(f"  provider={args.provider}  exchange={args.exchange}  codes={len(base_codes)}")
    print(f"  sector_map={len(sector_map)}종목  listen={args.listen_seconds}s  interval={args.summary_interval}s")
    print()

    stats: dict = {
        "total_messages": 0, "total_ingested_rows": 0,
        "total_snapshots": 0, "final_snapshot": None, "elapsed_seconds": 0.0,
        "registered_count": len(base_codes),
        "jsonl_path": str(jsonl_path) if jsonl_path else None,
    }
    t0 = time.monotonic()
    jsonl_file = open(jsonl_path, "w", encoding="utf-8") if jsonl_path else None
    try:
        if args.provider == "mock":
            await _run_mock_provider(
                service, base_codes, args.exchange,
                args.listen_seconds, args.summary_interval,
                stats, jsonl_file, args.verbose,
            )
        else:
            await _run_websocket_provider(
                service, base_codes, args.exchange,
                args.listen_seconds, args.summary_interval,
                stats, jsonl_file, args.verbose,
            )
    finally:
        if jsonl_file:
            jsonl_file.close()

    stats["elapsed_seconds"] = time.monotonic() - t0
    snap = service.get_snapshot()
    stats["final_snapshot"] = snap
    stats["final_status"] = snap.status
    stats["final_sector_count"] = snap.sector_count
    print(format_final_summary(stats))
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
