from __future__ import annotations

from datetime import datetime

import pytest

from src.intraday_state import IntradayQuoteState, normalize_tick


def test_intraday_quote_state_updates_latest_tick_by_code() -> None:
    state = IntradayQuoteState()
    received_at = datetime(2026, 6, 1, 9, 30, 0)

    state.update_tick(
        {
            "code": "5930",
            "name": "삼성전자",
            "current_price": "+70000",
            "open_price": "69000",
            "prev_close": "68000",
            "change_rate": "+2.94",
            "volume": "1,000",
            "accumulated_trade_value": "70,000,000",
            "minute_trade_value": "1,000,000",
        },
        received_at=received_at,
    )
    state.update_tick({"code": "005930", "current_price": "70100"}, received_at=received_at)

    frame = state.to_frame()

    assert len(frame) == 1
    assert frame.iloc[0]["code"] == "005930"
    assert frame.iloc[0]["name"] == "삼성전자"
    assert frame.iloc[0]["current_price"] == 70100.0
    assert frame.iloc[0]["accumulated_trade_value"] == 70_000_000.0


def test_normalize_tick_accepts_kiwoom_raw_values_shape() -> None:
    tick = {
        "item": "000660",
        "name": "주식체결",
        "values": {
            "10": "+232400",
            "12": "+1.23",
            "13": "988086",
            "14": "2284922",
            "15": "+156",
            "16": "+229900",
        },
    }

    row = normalize_tick(tick, received_at=datetime(2026, 6, 1, 9, 30, 0))

    assert row["code"] == "000660"
    assert row["current_price"] == 232400.0
    assert row["change_rate"] == 1.23
    assert row["volume"] == 988086.0
    assert row["accumulated_trade_value"] == 2284922.0
    assert row["updated_at"] == "2026-06-01T09:30:00"


def test_intraday_quote_state_rejects_missing_code() -> None:
    state = IntradayQuoteState()

    with pytest.raises(ValueError):
        state.update_tick({"current_price": 100})
