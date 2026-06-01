"""Bulk Kiwoom WebSocket smoke test.

Registers multiple stock codes across KRX/NXT/SOR exchanges and reports
per-item / per-exchange tick statistics. No order or account APIs are used.

Usage examples
--------------
# mock 로컬 확인
python scripts/test_kiwoom_ws_bulk.py \\
    --provider mock --exchange krx \\
    --codes 000660,005930 --listen-seconds 5 --max-messages 5

# 5종목 SOR prod
python scripts/test_kiwoom_ws_bulk.py \\
    --provider websocket --kiwoom-env prod --exchange sor \\
    --codes 000660,005930,035720,000080,003490 --listen-seconds 30

# codes-file 기반 50종목 NXT, JSONL 저장
python scripts/test_kiwoom_ws_bulk.py \\
    --provider websocket --kiwoom-env prod --exchange nxt \\
    --codes-file data/universe_codes.txt --max-codes 50 \\
    --listen-seconds 60 --dump-raw-jsonl

# exchange=all: 각 base code에 krx+nxt+sor 동시 등록
python scripts/test_kiwoom_ws_bulk.py \\
    --provider websocket --kiwoom-env prod --exchange all \\
    --codes 000660,005930 --listen-seconds 30
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.kiwoom_auth import (
    KiwoomApiConfig,
    KiwoomAuthError,
    issue_access_token,
    load_kiwoom_api_config,
)
from src.kiwoom_websocket import (
    KiwoomRawMessage,
    KiwoomWebSocketClient,
    KiwoomWebSocketError,
    format_kiwoom_code,
    normalize_tick_rows,
    parse_item_code,
)

# Credential fields must never appear in log files.
_SENSITIVE_KEYS = frozenset({"token", "appkey", "secretkey", "app_key", "secret_key"})


# ---------------------------------------------------------------------------
# Code-handling helpers (unit-testable)
# ---------------------------------------------------------------------------


def parse_codes_file(path: Path) -> list[str]:
    """Read a codes file and return unique valid codes (zero-padded to 6 digits).

    File format:
      - One code per line
      - Blank lines are ignored
      - Lines starting with '#' are treated as comments
      - Codes shorter than 6 digits are zero-padded (e.g. '5930' -> '005930')
      - Codes longer than 6 digits or non-numeric are excluded with a warning
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: dict[str, None] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.isdigit() and 1 <= len(line) <= 6:
            seen[line.zfill(6)] = None
        else:
            print(f"[warn] skipping invalid code: {raw_line!r}")
    return list(seen.keys())


def validate_codes(raw_codes: list[str]) -> tuple[list[str], list[str]]:
    """Validate a list of raw code strings from CLI.

    Returns (valid_codes, invalid_codes).
    valid_codes are deduplicated, zero-padded to 6 digits.
    """
    seen: dict[str, None] = {}
    invalid: list[str] = []
    for raw in raw_codes:
        stripped = str(raw).strip()
        if stripped.isdigit() and 1 <= len(stripped) <= 6:
            seen[stripped.zfill(6)] = None
        else:
            invalid.append(raw)
    return list(seen.keys()), invalid


def apply_max_codes(codes: list[str], max_codes: int) -> list[str]:
    """Truncate code list to max_codes (0 = no limit)."""
    if max_codes <= 0:
        return codes
    return codes[:max_codes]


def format_bulk_codes(base_codes: list[str], exchange: str) -> list[str]:
    """Format base codes with the given exchange suffix.

    exchange='all' registers krx + nxt + sor for each base code (3× count).
    Other values use a single suffix per code.
    """
    if exchange == "all":
        result: list[str] = []
        for code in base_codes:
            result.append(format_kiwoom_code(code, "krx"))
            result.append(format_kiwoom_code(code, "nxt"))
            result.append(format_kiwoom_code(code, "sor"))
        return result
    return [format_kiwoom_code(c, exchange) for c in base_codes]


def build_reg_groups(
    formatted_codes: list[str],
    batch_size: int = 200,
) -> list[tuple[str, list[str]]]:
    """Split formatted_codes into REG groups of at most batch_size.

    Kiwoom WebSocket REG 한 그룹당 최대 200종목 제한 (return_code=105118).
    Returns list of (group_no_str, codes_chunk); group_no starts at "1".
    """
    if batch_size <= 0:
        raise ValueError(f"batch_size must be positive, got {batch_size}")
    groups: list[tuple[str, list[str]]] = []
    for i, start in enumerate(range(0, len(formatted_codes), batch_size), start=1):
        groups.append((str(i), formatted_codes[start : start + batch_size]))
    return groups


def format_reg_summary(
    reg_results: dict[str, bool | None],
    total_groups: int,
) -> str:
    """Format REG result string for final summary.

    Single group  : "OK" / "FAILED"
    Multi all-OK  : "OK groups=2/2"
    Multi partial : "PARTIAL groups=1/2 failed_groups=2"
    Multi all-fail: "FAILED groups=0/2"
    """
    if not reg_results or total_groups == 0:
        return "N/A"
    ok_count = sum(1 for v in reg_results.values() if v is True)
    if total_groups <= 1:
        val = next(iter(reg_results.values()), None)
        if val is True:
            return "OK"
        if val is False:
            return "FAILED"
        return "N/A"
    failed_groups = [k for k, v in sorted(reg_results.items()) if v is False]
    if ok_count == total_groups:
        return f"OK groups={ok_count}/{total_groups}"
    if ok_count > 0:
        return f"PARTIAL groups={ok_count}/{total_groups} failed_groups={','.join(failed_groups)}"
    return f"FAILED groups=0/{total_groups}"


# ---------------------------------------------------------------------------
# Stats accumulator (unit-testable)
# ---------------------------------------------------------------------------


@dataclass
class BulkTickAccumulator:
    """Accumulate per-item / per-exchange REAL tick statistics."""

    start_time: float = field(default_factory=time.monotonic)
    total_messages: int = 0
    total_rows: int = 0
    rows_by_item: dict[str, int] = field(default_factory=dict)
    rows_by_exchange: dict[str, int] = field(default_factory=dict)

    def add_message(self, message: KiwoomRawMessage) -> int:
        """Process one raw message. Returns the number of REAL rows added."""
        self.total_messages += 1
        rows = normalize_tick_rows(message.raw)
        for row in rows:
            item = row.get("item") or ""
            exchange = row.get("exchange") or "unknown"
            self.rows_by_item[item] = self.rows_by_item.get(item, 0) + 1
            self.rows_by_exchange[exchange] = self.rows_by_exchange.get(exchange, 0) + 1
        self.total_rows += len(rows)
        return len(rows)

    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    def rows_per_sec(self) -> float:
        e = self.elapsed()
        return self.total_rows / e if e > 0 else 0.0

    def top_items(self, n: int) -> list[tuple[str, int]]:
        return sorted(self.rows_by_item.items(), key=lambda x: -x[1])[:n]

    def unique_base_codes(self) -> set[str]:
        return {parse_item_code(item)["base_code"] for item in self.rows_by_item}


# ---------------------------------------------------------------------------
# JSONL / diagnostic helpers
# ---------------------------------------------------------------------------


def _sanitize_response(parsed: dict) -> dict:
    """Strip credential fields from a parsed response dict."""
    return {k: v for k, v in parsed.items() if k.lower() not in _SENSITIVE_KEYS}


def _print_sanitized_response(label: str, parsed: dict) -> None:
    """Print a sanitized WebSocket response for diagnostics."""
    safe = _sanitize_response(parsed)
    print(f"{label}:")
    print(f"  return_code = {safe.get('return_code', '(absent)')}")
    print(f"  return_msg  = {safe.get('return_msg', '(absent)')}")
    print(f"  response_keys = {list(safe.keys())}")
    print(f"  raw_sanitized = {json.dumps(safe, ensure_ascii=False)[:400]}")


def _sanitize_for_log(raw: str) -> dict:
    """Strip credential fields before writing to a log file."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"_unparseable": raw[:500]}
    if not isinstance(parsed, dict):
        return {"_raw": str(parsed)[:500]}
    return _sanitize_response(parsed)


def _write_jsonl_record(f, message: KiwoomRawMessage, exchange: str) -> None:
    sanitized = _sanitize_for_log(message.raw)
    record = {"received_at": message.received_at, "exchange": exchange, **sanitized}
    f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _default_jsonl_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "logs" / f"kiwoom_ws_raw_bulk_{ts}.jsonl"


def _try_parse_json(raw: str) -> dict:
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def _print_startup_summary(
    config: KiwoomApiConfig,
    exchange: str,
    base_codes: list[str],
    formatted_codes: list[str],
    reg_groups: list[tuple[str, list[str]]],
    args: argparse.Namespace,
) -> None:
    print("[bulk] ===== startup =====")
    print(f"  env={config.env}  provider={config.provider}  exchange={exchange}")
    if config.provider == "mock":
        print("  rest_host = (not used by mock provider)")
        print("  ws_url    = (not used by mock provider)")
        print("  app_key   = (not used by mock provider)")
    else:
        print(f"  rest_host = {config.rest_host}")
        print(f"  ws_url    = {config.ws_url}")
        print(f"  app_key   = {_mask_key(config.app_key)}")
    print(f"  base_code_count      = {len(base_codes)}")
    print(f"  formatted_code_count = {len(formatted_codes)}")
    print(f"  reg_batch_size       = {args.reg_batch_size}")
    print(f"  reg_group_count      = {len(reg_groups)}")
    max_msg_str = str(args.max_messages) if args.max_messages > 0 else "∞"
    print(f"  listen_seconds={args.listen_seconds}  max_messages={max_msg_str}")
    print(f"  summary_interval={args.summary_interval}s")
    for grp_no, grp_codes in reg_groups:
        examples = ", ".join(grp_codes[:5])
        suffix = "..." if len(grp_codes) > 5 else ""
        print(f"  REG group {grp_no}: {len(grp_codes)} items, examples: {examples}{suffix}")
    print()


def _print_interval_summary(acc: BulkTickAccumulator) -> None:
    elapsed = acc.elapsed()
    print(f"[bulk] --- {elapsed:.0f}s elapsed ---")
    print(
        f"  messages={acc.total_messages}  rows={acc.total_rows}"
        f"  rows/sec={acc.rows_per_sec():.2f}"
    )
    print(
        f"  unique_base_codes={len(acc.unique_base_codes())}"
        f"  unique_items={len(acc.rows_by_item)}"
    )
    if acc.rows_by_exchange:
        exc_str = "  ".join(f"{k}:{v}" for k, v in sorted(acc.rows_by_exchange.items()))
        print(f"  by_exchange: {exc_str}")
    top = acc.top_items(10)
    if top:
        top_str = "  ".join(f"{item}:{cnt}" for item, cnt in top)
        print(f"  top_items: {top_str}")
    print()


def _print_final_summary(
    acc: BulkTickAccumulator,
    login_ok: bool,
    reg_results: dict[str, bool | None],
    total_groups: int,
    base_codes: list[str],
    formatted_codes: list[str],
    provider: str,
    ws_close_reason: str | None = None,
) -> None:
    if provider == "websocket":
        reg_label = format_reg_summary(reg_results, total_groups)
    else:
        reg_label = "N/A"
    print("[bulk] ===== final summary =====")
    print(f"  LOGIN={'OK' if login_ok else 'FAILED'}  REG={reg_label}")
    if ws_close_reason is not None:
        print(f"  connection_closed=YES  close_reason={ws_close_reason}")
    print(f"  total_messages={acc.total_messages}  total_rows={acc.total_rows}")
    print(f"  elapsed={acc.elapsed():.1f}s  rows/sec={acc.rows_per_sec():.2f}")
    print(f"  registered_codes={len(formatted_codes)}  base_codes={len(base_codes)}")
    if acc.rows_by_exchange:
        exc_str = "  ".join(f"{k}:{v}" for k, v in sorted(acc.rows_by_exchange.items()))
        print(f"  by_exchange: {exc_str}")
    top20 = acc.top_items(20)
    if top20:
        print(f"  top_active_items ({len(top20)}):")
        for item, cnt in top20:
            print(f"    {item}: {cnt} rows")
    seen_items = set(acc.rows_by_item.keys())
    no_tick = [c for c in base_codes if not any(c in item for item in seen_items)]
    if no_tick:
        print(f"  no_tick_base_codes={len(no_tick)}")
    print()


def _print_dry_run_plan(
    base_codes: list[str],
    formatted_codes: list[str],
    reg_groups: list[tuple[str, list[str]]],
    args: argparse.Namespace,
    over_limit: bool = False,
) -> None:
    print("[bulk] ===== DRY RUN (no WebSocket connection) =====")
    print(f"  exchange             = {args.exchange}")
    print(f"  base_code_count      = {len(base_codes)}")
    print(f"  formatted_code_count = {len(formatted_codes)}")
    print(f"  reg_batch_size       = {args.reg_batch_size}")
    print(f"  reg_group_count      = {len(reg_groups)}")
    for grp_no, grp_codes in reg_groups:
        examples = ", ".join(grp_codes[:5])
        suffix = "..." if len(grp_codes) > 5 else ""
        print(f"  REG group {grp_no}: {len(grp_codes)} items, examples: {examples}{suffix}")
    if over_limit and not args.allow_over_200_experimental:
        print(
            f"  [WARNING] formatted_code_count={len(formatted_codes)} > "
            f"max_total_realtime_codes={args.max_total_realtime_codes}. "
            f"실전 WebSocket 등록 시 차단됩니다 (105115 확인). "
            f"--max-codes {args.max_total_realtime_codes} 로 줄이거나 "
            f"--allow-over-200-experimental 지정 필요."
        )
    elif over_limit and args.allow_over_200_experimental:
        print(
            f"  [WARNING] {len(formatted_codes)}종목 > {args.max_total_realtime_codes}. "
            f"--allow-over-200-experimental 지정됨. 실전 실패 가능성 높음."
        )
    print()


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bulk Kiwoom WebSocket smoke test — verifies large-scale code registration "
            "and reports per-item/exchange tick counts. No order/account APIs are used."
        ),
    )
    parser.add_argument(
        "--codes", default="", help="Comma-separated 6-digit stock codes.",
    )
    parser.add_argument(
        "--codes-file", dest="codes_file", default="",
        help="Path to text file with one code per line (blank lines and # comments ignored).",
    )
    parser.add_argument(
        "--max-codes", dest="max_codes", type=int, default=0,
        help="Limit to first N base codes after dedup (0 = no limit).",
    )
    parser.add_argument(
        "--provider", choices=["mock", "rest", "websocket"],
        help="Override INTRADAY_PROVIDER for this run.",
    )
    parser.add_argument(
        "--kiwoom-env", choices=["mock", "prod", "real"], dest="kiwoom_env",
        help="'prod'/'real' -> api.kiwoom.com + KIWOOM_REAL_APP_KEY. 'mock' -> mockapi.",
    )
    parser.add_argument(
        "--exchange", choices=["krx", "nxt", "sor", "all"], default="krx",
        help=(
            "Exchange suffix. 'all' registers krx+nxt+sor for every base code (3× count). "
            "Default: krx"
        ),
    )
    parser.add_argument("--listen-seconds", dest="listen_seconds", type=float, default=30.0)
    parser.add_argument(
        "--max-messages", dest="max_messages", type=int, default=0,
        help="Stop after N REAL messages (0 = no limit).",
    )
    parser.add_argument(
        "--summary-interval-seconds", dest="summary_interval", type=float, default=10.0,
    )
    parser.add_argument(
        "--dump-raw-jsonl", dest="dump_raw_jsonl", metavar="FILE",
        nargs="?", const="", default=None,
        help=(
            "Save raw payloads to JSONL (credentials stripped). "
            "Default path: logs/kiwoom_ws_raw_bulk_YYYYMMDD_HHMMSS.jsonl"
        ),
    )
    parser.add_argument(
        "--reg-batch-size", dest="reg_batch_size", type=int, default=200,
        help=(
            "Maximum codes per REG group. "
            "Kiwoom 서버 한 그룹당 최대 200종목 제한 (return_code=105118). "
            "200 초과 시 자동으로 여러 그룹으로 분할. Default: 200"
        ),
    )
    parser.add_argument(
        "--max-total-realtime-codes", dest="max_total_realtime_codes", type=int, default=200,
        help=(
            "실전 WebSocket 총 실시간 등록 상한 (확인된 제한: 200종목). "
            "이 값을 초과하면 provider=websocket 실행이 차단됩니다. Default: 200"
        ),
    )
    parser.add_argument(
        "--allow-over-200-experimental", dest="allow_over_200_experimental",
        action="store_true", default=False,
        help=(
            "200종목 초과 등록을 강제로 시도합니다. 실험용. "
            "실전에서 return_code=105115로 실패할 가능성이 높습니다."
        ),
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=False,
        help=(
            "REG chunking 계획만 출력하고 WebSocket 연결하지 않음. "
            "API 키 불필요. 300종목 분할 계획 사전 확인용."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Provider runners
# ---------------------------------------------------------------------------


async def _run_mock_or_rest(
    provider,
    formatted_codes: list[str],
    args: argparse.Namespace,
    acc: BulkTickAccumulator,
    jsonl_file,
) -> None:
    """Run with mock or REST provider (bounded, no real WebSocket)."""
    max_msgs = args.max_messages if args.max_messages > 0 else 20
    messages = await provider.collect_raw_messages(
        formatted_codes,
        max_messages=max_msgs,
        listen_seconds=args.listen_seconds,
    )
    for msg in messages:
        acc.add_message(msg)
        if jsonl_file is not None:
            _write_jsonl_record(jsonl_file, msg, args.exchange)


async def _run_websocket(
    config: KiwoomApiConfig,
    formatted_codes: list[str],
    reg_groups: list[tuple[str, list[str]]],
    args: argparse.Namespace,
    acc: BulkTickAccumulator,
    jsonl_file,
) -> tuple[bool, dict[str, bool | None], str | None]:
    """Connect, register, and receive REAL messages.

    Returns (login_ok, reg_results, ws_close_reason).
    - login_ok: False only when LOGIN itself failed (before REG).
    - reg_results: grp_no -> True/False/None.
    - ws_close_reason: None = normal timeout expiry; str = server close message or error.
    """
    token = issue_access_token(
        config.rest_host,
        config.app_key,
        config.secret_key,
        timeout=15.0,
    )
    client = KiwoomWebSocketClient(config.ws_url, token, connect_timeout=15.0)

    login_ok = False
    reg_results: dict[str, bool | None] = {grp_no: None for grp_no, _ in reg_groups}
    expected_grp_nos = [grp_no for grp_no, _ in reg_groups]
    reg_response_count = 0
    ws_close_reason: str | None = None

    loop = asyncio.get_running_loop()
    next_summary_time = loop.time() + args.summary_interval

    try:
        async with client:
            async for msg in client.iter_raw_messages(
                formatted_codes,
                listen_seconds=args.listen_seconds,
                include_control_messages=True,
                reg_groups=reg_groups,
            ):
                parsed = _try_parse_json(msg.raw)
                trnm = parsed.get("trnm", "")

                if trnm == "LOGIN":
                    login_ok = True
                    continue

                if trnm == "PING":
                    continue

                if trnm == "REG":
                    resp_grp = str(parsed.get("grp_no", "")).strip() or None
                    if resp_grp and resp_grp in reg_results:
                        target_grp = resp_grp
                    elif reg_response_count < len(expected_grp_nos):
                        target_grp = expected_grp_nos[reg_response_count]
                    else:
                        target_grp = str(reg_response_count + 1)

                    rc_raw = parsed.get("return_code")
                    rc = int(rc_raw if rc_raw is not None else 0)
                    ok = rc == 0
                    reg_results[target_grp] = ok
                    reg_response_count += 1

                    if ok:
                        print(f"[bulk] REG group {target_grp}=OK")
                    else:
                        print(f"[bulk] REG group {target_grp}=FAILED")
                        _print_sanitized_response(
                            f"[bulk] REG group {target_grp} details", parsed
                        )
                    continue

                if trnm == "REAL":
                    acc.add_message(msg)
                    if jsonl_file is not None:
                        _write_jsonl_record(jsonl_file, msg, args.exchange)

                if loop.time() >= next_summary_time:
                    _print_interval_summary(acc)
                    next_summary_time = loop.time() + args.summary_interval

                if args.max_messages > 0 and acc.total_messages >= args.max_messages:
                    break

    except KiwoomWebSocketError as exc:
        exc_msg = str(exc)
        # "received 1000 (OK)" = server normal close, not an authentication failure.
        if "1000 (OK)" in exc_msg:
            raw_reason = exc_msg.split("receive failed: ")[-1] if "receive failed: " in exc_msg else exc_msg
            print(f"[bulk] WebSocket closed by server: {raw_reason}")
            ws_close_reason = raw_reason
            # login_ok is preserved — server closed after successful LOGIN+REG.
        else:
            print(f"[bulk] WebSocket error: {exc}")
            ws_close_reason = exc_msg

    return login_ok, reg_results, ws_close_reason


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run() -> int:
    args = _parse_args()

    if args.provider:
        os.environ["INTRADAY_PROVIDER"] = args.provider
    if args.kiwoom_env:
        os.environ["KIWOOM_ENV"] = args.kiwoom_env

    # Warn when kiwoom-env=prod but provider=mock (not a real WebSocket test).
    effective_env = os.environ.get("KIWOOM_ENV", "mock")
    if effective_env in ("prod", "real") and os.environ.get("INTRADAY_PROVIDER") == "mock":
        print(
            "[bulk] WARNING: kiwoom-env=prod but provider=mock. "
            "This is NOT a real WebSocket test — mock provider generates synthetic data."
        )

    # Mock + NXT/SOR warning.
    if effective_env == "mock" and args.exchange in ("nxt", "sor", "all"):
        print(
            "[bulk] WARNING: mock environment may support KRX only; "
            "use --kiwoom-env prod --provider websocket to verify NXT/SOR quotes."
        )

    # ---- Collect base codes ----
    raw_from_cli = [c.strip() for c in args.codes.split(",") if c.strip()]
    valid_cli, invalid_cli = validate_codes(raw_from_cli)
    for bad in invalid_cli:
        print(f"[warn] --codes: skipping invalid code: {bad!r}")

    file_codes: list[str] = []
    if args.codes_file:
        path = Path(args.codes_file)
        if not path.exists():
            print(f"[bulk] error: --codes-file not found: {path}")
            return 2
        file_codes = parse_codes_file(path)

    seen: dict[str, None] = {}
    for c in valid_cli + file_codes:
        seen[c] = None
    base_codes = apply_max_codes(list(seen.keys()), args.max_codes)

    if not base_codes:
        print("[bulk] error: no valid codes provided. Use --codes or --codes-file.")
        return 2

    formatted_codes = format_bulk_codes(base_codes, args.exchange)
    reg_groups = build_reg_groups(formatted_codes, args.reg_batch_size)

    # ---- Realtime code limit (Kiwoom: 200종목/세션 확인됨, 105115) ----
    over_limit = len(formatted_codes) > args.max_total_realtime_codes
    if over_limit and not args.allow_over_200_experimental:
        if args.provider == "websocket" and not args.dry_run:
            print(
                f"[bulk] ERROR: formatted_code_count={len(formatted_codes)} > "
                f"--max-total-realtime-codes={args.max_total_realtime_codes}. "
                f"Kiwoom WebSocket 실시간 등록 상한 200종목 확인됨 (return_code=105115). "
                f"--max-codes {args.max_total_realtime_codes} 로 줄이거나 "
                f"--allow-over-200-experimental 플래그 사용 (실패 가능성 높음)."
            )
            return 2
    elif over_limit and args.allow_over_200_experimental and not args.dry_run:
        print(
            f"[bulk] WARNING: {len(formatted_codes)}종목 > {args.max_total_realtime_codes} 상한. "
            f"--allow-over-200-experimental 지정됨. 실전 실패 가능성 높음 (105115)."
        )

    # ---- Dry run ----
    if args.dry_run:
        _print_dry_run_plan(base_codes, formatted_codes, reg_groups, args, over_limit)
        return 0

    # ---- Config ----
    try:
        config = load_kiwoom_api_config()
    except KiwoomAuthError as exc:
        print(f"[bulk] config error: {exc}")
        return 2

    # ---- JSONL path ----
    jsonl_path: Path | None = None
    if args.dump_raw_jsonl is not None:
        jsonl_path = (
            Path(args.dump_raw_jsonl) if args.dump_raw_jsonl else _default_jsonl_path()
        )
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[bulk] raw JSONL dump -> {jsonl_path}")

    _print_startup_summary(config, args.exchange, base_codes, formatted_codes, reg_groups, args)

    acc = BulkTickAccumulator()
    login_ok = True        # mock/rest always treat as OK
    reg_results: dict[str, bool | None] = {}
    ws_close_reason: str | None = None

    jsonl_file = open(jsonl_path, "w", encoding="utf-8") if jsonl_path else None
    try:
        if config.provider == "websocket":
            login_ok, reg_results, ws_close_reason = await _run_websocket(
                config, formatted_codes, reg_groups, args, acc, jsonl_file
            )
        else:
            from src.data_providers import build_raw_market_data_provider
            provider = build_raw_market_data_provider(config)
            await _run_mock_or_rest(provider, formatted_codes, args, acc, jsonl_file)
    except (KiwoomAuthError, Exception) as exc:
        print(f"[bulk] error: {type(exc).__name__}: {exc}")
        return 2
    finally:
        if jsonl_file is not None:
            jsonl_file.close()
            if jsonl_path:
                print(f"[bulk] {acc.total_messages} record(s) written to {jsonl_path}")

    _print_final_summary(
        acc, login_ok, reg_results, len(reg_groups), base_codes, formatted_codes,
        config.provider, ws_close_reason=ws_close_reason,
    )

    if not acc.total_rows:
        print(
            "[bulk] no REAL rows received. "
            "If outside 08:00–18:00 KST, market data may not be streaming. "
            "Re-run during pre-market (08:00~) or market hours."
        )
        return 1

    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
