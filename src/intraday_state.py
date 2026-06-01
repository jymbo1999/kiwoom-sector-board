from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

import pandas as pd


QUOTE_COLUMNS = [
    "code",
    "name",
    "current_price",
    "open_price",
    "prev_close",
    "change_rate",
    "volume",
    "trade_value",
    "accumulated_trade_value",
    "minute_trade_value",
    "updated_at",
]


@dataclass
class IntradayQuoteState:
    """In-memory latest quote state for future WebSocket adapter integration."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def update_tick(self, tick: Mapping[str, Any], *, received_at: datetime | None = None) -> dict[str, Any]:
        normalized = normalize_tick(tick, received_at=received_at)
        code = normalized.get("code")
        if not code:
            raise ValueError("tick is missing a stock code.")
        current = dict(self.rows.get(str(code), {}))
        current.update({k: v for k, v in normalized.items() if v not in (None, "")})
        self.rows[str(code)] = current
        return current

    def update_many(self, ticks: list[Mapping[str, Any]], *, received_at: datetime | None = None) -> None:
        for tick in ticks:
            self.update_tick(tick, received_at=received_at)

    def to_frame(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=QUOTE_COLUMNS)
        frame = pd.DataFrame(self.rows.values())
        for column in QUOTE_COLUMNS:
            if column not in frame:
                frame[column] = 0.0 if column not in {"code", "name", "updated_at"} else ""
        return frame[QUOTE_COLUMNS].sort_values("code").reset_index(drop=True)


def normalize_tick(tick: Mapping[str, Any], *, received_at: datetime | None = None) -> dict[str, Any]:
    values = tick.get("values") if isinstance(tick.get("values"), Mapping) else {}
    timestamp = (received_at or datetime.now()).isoformat(timespec="seconds")
    code = tick.get("code") or tick.get("item") or tick.get("stk_cd") or tick.get("ticker")
    return {
        "code": _normalize_code(code),
        "name": str(tick.get("name") or tick.get("stock_name") or ""),
        "current_price": _num(_first_present(tick, values, "current_price", "10")),
        "open_price": _num(_first_present(tick, values, "open_price", "16")),
        "prev_close": _num(_first_present(tick, values, "prev_close", "")),
        "change_rate": _num(_first_present(tick, values, "change_rate", "12")),
        "volume": _num(_first_present(tick, values, "volume", "13")),
        "trade_value": _num(_first_present(tick, values, "trade_value", "14")),
        "accumulated_trade_value": _num(_first_present(tick, values, "accumulated_trade_value", "14")),
        "minute_trade_value": _num(_first_present(tick, values, "minute_trade_value", "15")),
        "updated_at": str(tick.get("updated_at") or timestamp),
    }


def _normalize_code(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def _first_present(tick: Mapping[str, Any], values: Mapping[str, Any], tick_key: str, value_key: str) -> object | None:
    if tick_key in tick:
        return tick.get(tick_key)
    if value_key and value_key in values:
        return values.get(value_key)
    return None


def _num(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text.startswith("+"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return 0.0
