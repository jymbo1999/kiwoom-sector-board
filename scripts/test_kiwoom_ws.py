from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_providers import DEFAULT_TEST_CODES, build_raw_market_data_provider
from src.kiwoom_auth import KiwoomAuthError, load_kiwoom_api_config
from src.kiwoom_websocket import (
    EXCHANGE_SUFFIX,
    TYPE_0B_FIELD_MAP,
    KiwoomRawMessage,
    format_kiwoom_code,
    normalize_tick_rows,
)

# Credential fields that must never be written to log files.
_SENSITIVE_KEYS = frozenset({"token", "appkey", "secretkey", "app_key", "secret_key"})


def _parse_codes(value: str) -> list[str]:
    codes = [item.strip().zfill(6) for item in value.split(",") if item.strip()]
    return codes or DEFAULT_TEST_CODES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Kiwoom intraday quote connectivity without using order/account APIs.",
    )
    parser.add_argument(
        "--codes",
        default=",".join(DEFAULT_TEST_CODES),
        help="Comma-separated stock codes (6-digit KRX format). Default: 005930,000660",
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "rest", "websocket"],
        help="Override INTRADAY_PROVIDER for this run.",
    )
    parser.add_argument(
        "--kiwoom-env",
        choices=["mock", "prod", "real"],
        dest="kiwoom_env",
        help=(
            "'prod'/'real' -> api.kiwoom.com + KIWOOM_REAL_APP_KEY. "
            "'mock' -> mockapi.kiwoom.com + KIWOOM_MOCK_APP_KEY."
        ),
    )
    parser.add_argument(
        "--exchange",
        choices=list(EXCHANGE_SUFFIX.keys()),
        default="krx",
        help=(
            "Exchange suffix for WebSocket REG item code. "
            "krx=plain, nxt=CODE_NX, sor/all=CODE_AL. Default: krx"
        ),
    )
    parser.add_argument("--max-messages", type=int, default=5)
    parser.add_argument("--listen-seconds", type=float, default=20.0)
    parser.add_argument(
        "--dump-raw-jsonl",
        dest="dump_raw_jsonl",
        metavar="FILE",
        nargs="?",
        const="",          # flag present but no path given → use default path
        default=None,      # flag absent
        help=(
            "Save received raw payloads to a JSONL file (one JSON object per line). "
            "Credentials are stripped before writing. "
            "Default path: logs/kiwoom_ws_raw_YYYYMMDD_HHMMSS.jsonl"
        ),
    )
    return parser.parse_args()


def _default_jsonl_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "logs" / f"kiwoom_ws_raw_{ts}.jsonl"


def _sanitize_for_log(raw: str) -> dict:
    """Parse raw JSON and strip credential fields before writing to a log file."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"_unparseable": raw[:500]}
    if not isinstance(parsed, dict):
        return {"_raw": str(parsed)[:500]}
    return {k: v for k, v in parsed.items() if k.lower() not in _SENSITIVE_KEYS}


def _format_message_block(msg_index: int, total: int, message: KiwoomRawMessage) -> str:
    """Format one received message for console output.

    Shows:
      - message index / total, received_at
      - trnm
      - data row count
      - per-row: row index, item, base_code, exchange, type, name, 0B field values
      - full raw payload (truncated at 600 chars)
    """
    lines: list[str] = [
        f"--- message {msg_index}/{total}  received_at={message.received_at} ---"
    ]

    try:
        parsed = json.loads(message.raw)
    except (json.JSONDecodeError, ValueError):
        lines.append(f"  [unparseable raw] {message.raw[:300]}")
        return "\n".join(lines)

    if not isinstance(parsed, dict):
        lines.append(f"  [raw] {message.raw[:300]}")
        return "\n".join(lines)

    trnm = parsed.get("trnm", "?")
    lines.append(f"  trnm={trnm}")

    data = parsed.get("data")
    if isinstance(data, list):
        lines.append(f"  data_rows={len(data)}")
        rows = normalize_tick_rows(parsed)
        if rows:
            for row_idx, row in enumerate(rows):
                parts = [
                    f"  [row {row_idx}]",
                    f"item={row['item']}",
                    f"base_code={row['base_code']}",
                    f"exchange={row['exchange']}",
                    f"type={row['type']}",
                    f"name={row['name']}",
                ]
                if row["trade_time"] is not None:
                    parts.append(f"trade_time={row['trade_time']}")
                if row["current_price"] is not None:
                    parts.append(f"current_price={row['current_price']}")
                if row["change_price"] is not None:
                    parts.append(f"change_price={row['change_price']}")
                if row["change_rate"] is not None:
                    parts.append(f"change_rate={row['change_rate']}")
                if row["trade_volume"] is not None:
                    parts.append(f"trade_volume={row['trade_volume']}")
                if row["accumulated_volume"] is not None:
                    parts.append(f"acc_vol={row['accumulated_volume']}")
                if row["accumulated_trade_value"] is not None:
                    parts.append(f"acc_val={row['accumulated_trade_value']}")
                # Show any unrecognized numeric keys not in TYPE_0B_FIELD_MAP
                known_indices = set(TYPE_0B_FIELD_MAP.keys())
                unknown = {k: v for k, v in row["raw_values"].items() if k not in known_indices}
                if unknown:
                    parts.append(f"unknown_fields={unknown}")
                lines.append("  " + "  ".join(parts))
        else:
            # data exists but entries are not dicts (e.g. control messages)
            for row_idx, entry in enumerate(data[:5]):
                lines.append(f"  [row {row_idx}] {str(entry)[:200]}")
    elif trnm not in ("REAL",):
        # Control message: show all non-sensitive top-level fields
        for k, v in parsed.items():
            if k.lower() not in _SENSITIVE_KEYS:
                lines.append(f"  {k}={v}")

    lines.append(f"  [raw({len(message.raw)})] {message.raw[:600]}")
    return "\n".join(lines)


async def _run() -> int:
    args = _parse_args()

    if args.provider:
        os.environ["INTRADAY_PROVIDER"] = args.provider
    if args.kiwoom_env:
        os.environ["KIWOOM_ENV"] = args.kiwoom_env

    exchange = args.exchange or "krx"
    base_codes = _parse_codes(args.codes)
    formatted_codes = [format_kiwoom_code(c, exchange) for c in base_codes]

    effective_env = os.environ.get("KIWOOM_ENV", "mock")
    if effective_env == "mock" and exchange in ("nxt", "sor", "all"):
        print(
            "[kiwoom-check] WARNING: mock environment may support KRX only; "
            "use --kiwoom-env prod to verify NXT/SOR quotes."
        )

    # Resolve JSONL dump path
    jsonl_path: Path | None = None
    if args.dump_raw_jsonl is not None:
        jsonl_path = (
            Path(args.dump_raw_jsonl) if args.dump_raw_jsonl else _default_jsonl_path()
        )
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[kiwoom-check] raw JSONL dump -> {jsonl_path}")

    try:
        config = load_kiwoom_api_config()
        provider = build_raw_market_data_provider(config)
        print(
            "[kiwoom-check] "
            f"env={config.env}  provider={config.provider}  exchange={exchange}\n"
            f"  rest_host={config.rest_host}\n"
            f"  ws_url={config.ws_url}\n"
            f"  base_codes={','.join(base_codes)}\n"
            f"  formatted_codes={','.join(formatted_codes)}"
        )
        messages = await provider.collect_raw_messages(
            formatted_codes,
            max_messages=max(1, args.max_messages),
            listen_seconds=max(1.0, args.listen_seconds),
        )
    except (KiwoomAuthError, Exception) as exc:
        print(f"[kiwoom-check] failed: {type(exc).__name__}: {exc}")
        return 2

    if not messages:
        print(
            "[kiwoom-check] connected but no messages received before timeout.\n"
            "  If outside 08:00–18:00 KST, NXT/SOR real-time quotes may not be streaming.\n"
            "  Re-run during pre-market (08:00~) or market hours for NXT validation."
        )
        return 1

    print(f"\n[kiwoom-check] received {len(messages)} message(s):\n")

    jsonl_file = open(jsonl_path, "w", encoding="utf-8") if jsonl_path else None
    try:
        for i, message in enumerate(messages, 1):
            print(_format_message_block(i, len(messages), message))
            print()

            if jsonl_file is not None:
                sanitized = _sanitize_for_log(message.raw)
                record = {
                    "received_at": message.received_at,
                    "exchange": exchange,
                    **sanitized,
                }
                jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        if jsonl_file is not None:
            jsonl_file.close()
            print(f"[kiwoom-check] {len(messages)} record(s) written to {jsonl_path}")

    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
