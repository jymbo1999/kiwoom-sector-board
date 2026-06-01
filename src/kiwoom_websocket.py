from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, AsyncIterator

from .kiwoom_auth import AccessToken


class KiwoomWebSocketError(RuntimeError):
    """Raised when a Kiwoom market-data WebSocket check fails."""


@dataclass(frozen=True)
class KiwoomRawMessage:
    raw: str
    received_at: str


# ---------------------------------------------------------------------------
# Exchange / market suffix — confirmed from prod REAL payload (2026-06-01)
# ---------------------------------------------------------------------------

EXCHANGE_SUFFIX: dict[str, str] = {
    "krx": "",
    "nxt": "_NX",  # 넥스트레이드 — confirmed prod
    "sor": "_AL",  # SOR / 통합 — confirmed prod
    "all": "_AL",  # alias for sor
}

# Reverse: suffix string → exchange name (non-empty suffixes only)
_SUFFIX_TO_EXCHANGE: dict[str, str] = {
    "_NX": "nxt",
    "_AL": "sor",
}

# ---------------------------------------------------------------------------
# Kiwoom WebSocket realtime type 0B (주식체결) field index mapping.
# Field indices confirmed from prod REAL payload (2026-06-01).
# best_ask / best_bid field indices are not yet confirmed — marked TODO.
# ---------------------------------------------------------------------------

TYPE_0B_FIELD_MAP: dict[str, str] = {
    "20": "trade_time",               # 체결시간 HHMMSS
    "10": "current_price",            # 현재가 (signed int string)
    "11": "change_price",             # 전일대비 (signed int string)
    "12": "change_rate",              # 등락률 % (signed float string)
    "15": "trade_volume",             # 체결량
    "13": "accumulated_volume",       # 누적거래량
    "14": "accumulated_trade_value",  # 누적거래대금
    # TODO: best_ask field index not confirmed from prod payload
    # TODO: best_bid field index not confirmed from prod payload
}


# ---------------------------------------------------------------------------
# Code formatting helpers
# ---------------------------------------------------------------------------

def format_kiwoom_code(code: str, exchange: str = "krx") -> str:
    """Append exchange suffix to a stock code for Kiwoom WebSocket REG.

    Suffix mapping (confirmed prod 2026-06-01):
      krx -> 000660
      nxt -> 000660_NX
      sor -> 000660_AL
      all -> 000660_AL  (SOR/unified, same as sor)

    Unknown exchange values are treated as KRX (no suffix).
    """
    normalized = str(code).strip().zfill(6)
    suffix = EXCHANGE_SUFFIX.get(exchange.lower(), "")
    return f"{normalized}{suffix}"


def parse_item_code(item: str) -> dict[str, str]:
    """Split a Kiwoom item code into raw_code, base_code, and exchange.

    Confirmed suffix mapping (prod 2026-06-01):
      "000660"    -> base_code="000660", exchange="krx"
      "000660_NX" -> base_code="000660", exchange="nxt"
      "000660_AL" -> base_code="000660", exchange="sor"
    """
    raw = str(item).strip()
    # Check longest suffix first to avoid partial matches
    for suffix, exchange in sorted(_SUFFIX_TO_EXCHANGE.items(), key=lambda x: -len(x[0])):
        if raw.upper().endswith(suffix.upper()):
            base_code = raw[: -len(suffix)]
            return {"raw_code": raw, "base_code": base_code, "exchange": exchange}
    return {"raw_code": raw, "base_code": raw, "exchange": "krx"}


# ---------------------------------------------------------------------------
# Numeric parsing helpers
# ---------------------------------------------------------------------------

def parse_signed_int(value: str | int | None) -> int | None:
    """Parse a Kiwoom signed numeric string to int.

    Python's int() already handles leading +/- signs.
    Returns None for empty or non-numeric input.

    Examples:
      "+2380000" -> 2380000
      "-10"      -> -10
      "1000"     -> 1000
      ""         -> None
      None       -> None
    """
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def parse_signed_float(value: str | float | None) -> float | None:
    """Parse a Kiwoom signed numeric string to float.

    Returns None for empty or non-numeric input.

    Examples:
      "+0.70" -> 0.70
      "-1.23" -> -1.23
      ""      -> None
    """
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Tick normalization
# ---------------------------------------------------------------------------

def _normalize_one_data_entry(
    entry: dict[str, Any],
    *,
    fallback_item: str | None = None,
    fallback_type: str | None = None,
    fallback_name: str | None = None,
) -> dict[str, Any]:
    """Normalize a single data-entry dict from a Kiwoom REAL message.

    Handles both numeric-keyed entries (prod 0B format) and
    named-key entries (mock provider format).
    """
    raw_item = str(entry.get("item") or fallback_item or "").strip() or None
    tick_type = str(entry.get("type") or fallback_type or "").strip() or None
    name = str(entry.get("name") or fallback_name or "").strip() or None

    # Split item code into base_code + exchange
    code_info = (
        parse_item_code(raw_item)
        if raw_item
        else {"raw_code": None, "base_code": None, "exchange": "krx"}
    )

    # Collect numeric-keyed values (prod format: "20", "10", ...)
    raw_values: dict[str, Any] = {
        k: v for k, v in entry.items() if k.isdigit()
    }

    # Map 0B field indices → named fields (prod format)
    fv: dict[str, Any] = {fname: raw_values.get(idx) for idx, fname in TYPE_0B_FIELD_MAP.items()}

    # Named fallbacks for mock / legacy format
    def _first(*keys: str) -> Any:
        for k in keys:
            v = entry.get(k)
            if v is not None:
                return v
        return None

    # trade_time: string, keep as-is
    trade_time_raw = fv["trade_time"]
    trade_time = str(trade_time_raw).strip() if trade_time_raw is not None else None

    # Numeric conversions — fall back to named keys if numeric key absent
    current_price = parse_signed_int(fv["current_price"] or _first("current_price", "stck_prpr", "close", "price"))
    change_price = parse_signed_int(fv["change_price"])
    change_rate = parse_signed_float(fv["change_rate"] or _first("change_rate"))
    trade_volume = parse_signed_int(fv["trade_volume"] or _first("trade_volume", "cntg_vol", "volume"))
    accumulated_volume = parse_signed_int(fv["accumulated_volume"])
    accumulated_trade_value = parse_signed_int(
        fv["accumulated_trade_value"] or _first("trade_value", "acml_tr_pbmn", "trade_amount")
    )

    return {
        "item": raw_item,
        "raw_code": code_info["raw_code"],
        "base_code": code_info["base_code"],
        "exchange": code_info["exchange"],
        "type": tick_type,
        "name": name,
        "trade_time": trade_time,
        "current_price": current_price,
        "change_price": change_price,
        "change_rate": change_rate,
        "trade_volume": trade_volume,
        "accumulated_volume": accumulated_volume,
        "accumulated_trade_value": accumulated_trade_value,
        "best_ask": None,   # TODO: field index not confirmed from prod payload
        "best_bid": None,   # TODO: field index not confirmed from prod payload
        "raw_values": raw_values,
    }


def normalize_tick_rows(raw_payload: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize all data rows in a Kiwoom REAL message, one dict per row.

    Returns an empty list when the payload has no parseable data entries.
    Each row dict has the same field structure as normalize_tick_message()
    but without the top-level raw/parsed keys.
    """
    if isinstance(raw_payload, str):
        try:
            parsed: Any = json.loads(raw_payload)
        except json.JSONDecodeError:
            return []
    else:
        parsed = raw_payload

    if not isinstance(parsed, dict):
        return []

    data = parsed.get("data")
    if not isinstance(data, list) or not data:
        # Handle flat REAL message (mock provider format: no nested "data" array).
        # The message itself acts as the single row entry.
        if parsed.get("trnm") == "REAL":
            fallback_item = str(parsed.get("code") or parsed.get("item") or "").strip() or None
            return [_normalize_one_data_entry(parsed, fallback_item=fallback_item)]
        return []

    rows: list[dict[str, Any]] = []
    for entry in data:
        if isinstance(entry, dict):
            rows.append(_normalize_one_data_entry(entry))
    return rows


def normalize_tick_message(raw_payload: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize a Kiwoom tick message to a consistent structure.

    Processes the first data row. For multi-row messages use normalize_tick_rows().
    Raw payload is always preserved.

    Return fields:
      raw, parsed                  — always present
      item, raw_code, base_code,   — code fields
      exchange, type, name
      trade_time                   — 체결시간 HHMMSS (str|None)
      current_price                — 현재가 (int|None)
      change_price                 — 전일대비 (int|None)
      change_rate                  — 등락률 % (float|None)
      trade_volume                 — 체결량 (int|None)
      accumulated_volume           — 누적거래량 (int|None)
      accumulated_trade_value      — 누적거래대금 (int|None)
      best_ask                     — None (TODO: index unconfirmed)
      best_bid                     — None (TODO: index unconfirmed)
      raw_values                   — numeric-keyed raw dict
    """
    if isinstance(raw_payload, str):
        try:
            parsed: Any = json.loads(raw_payload)
        except json.JSONDecodeError:
            parsed = None
    else:
        parsed = raw_payload

    rows = normalize_tick_rows(raw_payload)

    if rows:
        first_row = rows[0]
    else:
        first_row = {
            "item": None,
            "raw_code": None,
            "base_code": None,
            "exchange": "krx",
            "type": None,
            "name": None,
            "trade_time": None,
            "current_price": None,
            "change_price": None,
            "change_rate": None,
            "trade_volume": None,
            "accumulated_volume": None,
            "accumulated_trade_value": None,
            "best_ask": None,
            "best_bid": None,
            "raw_values": {},
        }

    return {"raw": raw_payload, "parsed": parsed, **first_row}


# ---------------------------------------------------------------------------
# REG payload builder
# ---------------------------------------------------------------------------

def build_realtime_trade_registration(
    codes: list[str],
    *,
    group_no: str = "1",
    realtime_type: str = "0B",
    refresh: bool = True,
) -> dict[str, Any]:
    """Build Kiwoom's market-data registration payload for stock executions."""
    normalized_codes = [str(code).zfill(6) for code in codes if str(code).strip()]
    if not normalized_codes:
        raise KiwoomWebSocketError("At least one stock code is required for WebSocket registration.")
    return {
        "trnm": "REG",
        "grp_no": str(group_no),
        "refresh": "1" if refresh else "0",
        "data": [
            {
                "item": normalized_codes,
                "type": [realtime_type],
            }
        ],
    }


# ---------------------------------------------------------------------------
# WebSocket client
# ---------------------------------------------------------------------------

class KiwoomWebSocketClient:
    """Small read-only Kiwoom market-data WebSocket client.

    Sends only LOGIN, REG, PING echo, and disconnect messages.
    No order, account, balance, correction, or cancellation endpoint is used.
    """

    def __init__(
        self,
        ws_url: str,
        access_token: AccessToken | str,
        *,
        connect_timeout: float = 10.0,
    ) -> None:
        self.ws_url = ws_url
        self.access_token = access_token.token if isinstance(access_token, AccessToken) else str(access_token)
        self.connect_timeout = connect_timeout
        self.websocket: Any | None = None
        self.connected = False

    async def __aenter__(self) -> "KiwoomWebSocketClient":
        await self.connect()
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise KiwoomWebSocketError(
                "The 'websockets' package is required. Install project requirements first."
            ) from exc
        try:
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.ws_url),
                timeout=self.connect_timeout,
            )
        except Exception as exc:
            self.connected = False
            raise KiwoomWebSocketError(f"Kiwoom WebSocket connection failed: {exc}") from exc
        self.connected = True

    async def disconnect(self) -> None:
        if self.websocket is not None:
            try:
                await self.websocket.close()
            finally:
                self.connected = False
                self.websocket = None

    async def send_message(self, message: str | dict[str, Any]) -> None:
        if not self.connected or self.websocket is None:
            raise KiwoomWebSocketError("Kiwoom WebSocket is not connected.")
        if not isinstance(message, str):
            message = json.dumps(message, ensure_ascii=False)
        await self.websocket.send(message)

    async def login(self) -> None:
        await self.send_message({"trnm": "LOGIN", "token": self.access_token})

    async def register_realtime_trades(
        self,
        codes: list[str],
        *,
        group_no: str = "1",
        realtime_type: str = "0B",
    ) -> None:
        await self.send_message(
            build_realtime_trade_registration(
                codes,
                group_no=group_no,
                realtime_type=realtime_type,
            )
        )

    async def receive_raw(self, timeout: float | None = None) -> str:
        if not self.connected or self.websocket is None:
            raise KiwoomWebSocketError("Kiwoom WebSocket is not connected.")
        try:
            if timeout is None:
                message = await self.websocket.recv()
            else:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            self.connected = False
            raise KiwoomWebSocketError(f"Kiwoom WebSocket receive failed: {exc}") from exc
        return message.decode("utf-8", errors="replace") if isinstance(message, bytes) else str(message)

    async def iter_raw_messages(
        self,
        codes: list[str],
        *,
        listen_seconds: float = 20.0,
        per_message_timeout: float = 5.0,
        include_control_messages: bool = True,
        reg_groups: list[tuple[str, list[str]]] | None = None,
    ) -> AsyncIterator[KiwoomRawMessage]:
        """Stream raw WebSocket messages.

        reg_groups: list of (group_no, codes_chunk) — when provided, each chunk is
        sent as a separate REG after LOGIN (handles Kiwoom's 200-item-per-group limit).
        When None, all codes are sent in a single REG (group_no="1").
        """
        await self.login()
        registered = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + listen_seconds

        while loop.time() < deadline:
            timeout = min(per_message_timeout, max(0.1, deadline - loop.time()))
            try:
                raw = await self.receive_raw(timeout=timeout)
            except asyncio.TimeoutError:
                continue

            parsed = _parse_json(raw)
            if parsed.get("trnm") == "PING":
                await self.send_message(parsed)
                if not include_control_messages:
                    continue

            if parsed.get("trnm") == "LOGIN":
                if int(parsed.get("return_code", 0) or 0) != 0:
                    raise KiwoomWebSocketError(
                        f"Kiwoom WebSocket login failed: {parsed.get('return_msg') or raw}"
                    )
                if not registered:
                    if reg_groups is not None:
                        for grp_no, grp_codes in reg_groups:
                            await self.register_realtime_trades(grp_codes, group_no=grp_no)
                    else:
                        await self.register_realtime_trades(codes)
                    registered = True
                if not include_control_messages:
                    continue

            yield KiwoomRawMessage(
                raw=raw,
                received_at=datetime.now().isoformat(timespec="seconds"),
            )

    async def collect_raw_messages(
        self,
        codes: list[str],
        *,
        max_messages: int = 5,
        listen_seconds: float = 20.0,
        include_control_messages: bool = True,
    ) -> list[KiwoomRawMessage]:
        messages: list[KiwoomRawMessage] = []
        async with self:
            async for message in self.iter_raw_messages(
                codes,
                listen_seconds=listen_seconds,
                include_control_messages=include_control_messages,
            ):
                messages.append(message)
                if len(messages) >= max_messages:
                    break
        return messages

    def stream_current_prices(self, codes: list[str]) -> Any:
        raise NotImplementedError(
            "Use collect_raw_messages() for the WebSocket validation step; "
            "DataFrame normalization will be added after raw payloads are confirmed."
        )


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
