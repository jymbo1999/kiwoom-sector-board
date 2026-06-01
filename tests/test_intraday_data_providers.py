from __future__ import annotations

import asyncio
import json

import pytest

from src.data_providers import MockQuoteProvider, build_raw_market_data_provider
from src.kiwoom_auth import (
    MOCK_REST_HOST,
    MOCK_WS_URL,
    REAL_REST_HOST,
    REAL_WS_URL,
    KiwoomAuthError,
    load_kiwoom_api_config,
)
from src.kiwoom_websocket import (
    build_realtime_trade_registration,
    format_kiwoom_code,
    normalize_tick_message,
    normalize_tick_rows,
    parse_item_code,
    parse_signed_int,
    parse_signed_float,
)


def test_load_kiwoom_api_config_mock_hosts() -> None:
    config = load_kiwoom_api_config(
        {
            "KIWOOM_ENV": "mock",
            "INTRADAY_PROVIDER": "websocket",
            "KIWOOM_APP_KEY": "app",
            "KIWOOM_SECRET_KEY": "secret",
        },
        load_env_file=False,
    )

    assert config.env == "mock"
    assert config.provider == "websocket"
    assert config.rest_host == MOCK_REST_HOST
    assert config.ws_url == MOCK_WS_URL
    assert config.secret_key == "secret"


def test_load_kiwoom_api_config_real_uses_real_keys() -> None:
    config = load_kiwoom_api_config(
        {
            "KIWOOM_ENV": "real",
            "INTRADAY_PROVIDER": "rest",
            "KIWOOM_REAL_APP_KEY": "real-app",
            "KIWOOM_REAL_SECRET_KEY": "real-secret",
        },
        load_env_file=False,
    )

    assert config.env == "real"
    assert config.provider == "rest"
    assert config.rest_host == REAL_REST_HOST
    assert config.ws_url == REAL_WS_URL
    assert config.app_key == "real-app"
    assert config.secret_key == "real-secret"


def test_load_kiwoom_api_config_rejects_orderless_provider_typos() -> None:
    with pytest.raises(KiwoomAuthError):
        load_kiwoom_api_config(
            {
                "KIWOOM_ENV": "mock",
                "INTRADAY_PROVIDER": "orders",
            },
            load_env_file=False,
        )


def test_build_realtime_trade_registration_uses_market_data_type_only() -> None:
    payload = build_realtime_trade_registration(["5930", "000660"])

    assert payload == {
        "trnm": "REG",
        "grp_no": "1",
        "refresh": "1",
        "data": [{"item": ["005930", "000660"], "type": ["0B"]}],
    }


def test_normalize_tick_message_preserves_raw_payload() -> None:
    raw = '{"trnm":"REAL","data":[["005930"]]}'

    normalized = normalize_tick_message(raw)

    assert normalized["raw"] == raw
    assert normalized["parsed"] == {"trnm": "REAL", "data": [["005930"]]}


def test_mock_quote_provider_returns_raw_messages() -> None:
    provider = MockQuoteProvider()

    messages = asyncio.run(provider.collect_raw_messages(["005930", "000660"], max_messages=2))

    assert len(messages) == 2
    payloads = [json.loads(message.raw) for message in messages]
    assert {payload["code"] for payload in payloads} == {"005930", "000660"}
    assert all(payload["provider"] == "mock" for payload in payloads)


def test_build_raw_market_data_provider_defaults_to_mock() -> None:
    config = load_kiwoom_api_config({}, load_env_file=False)

    provider = build_raw_market_data_provider(config)

    assert isinstance(provider, MockQuoteProvider)


# ---------------------------------------------------------------------------
# format_kiwoom_code
# ---------------------------------------------------------------------------


def test_format_kiwoom_code_krx_no_suffix() -> None:
    assert format_kiwoom_code("000660", "krx") == "000660"


def test_format_kiwoom_code_krx_zero_pads_short_code() -> None:
    assert format_kiwoom_code("5930", "krx") == "005930"


def test_format_kiwoom_code_nxt_appends_nx() -> None:
    # UNVERIFIED suffix — must be confirmed with prod NXT real-time quote
    assert format_kiwoom_code("000660", "nxt") == "000660_NX"


def test_format_kiwoom_code_nxt_zero_pads_short_code() -> None:
    assert format_kiwoom_code("5930", "nxt") == "005930_NX"


def test_format_kiwoom_code_sor_appends_al() -> None:
    # UNVERIFIED suffix — must be confirmed with prod SOR real-time quote
    assert format_kiwoom_code("000660", "sor") == "000660_AL"


def test_format_kiwoom_code_all_same_as_sor() -> None:
    assert format_kiwoom_code("000660", "all") == "000660_AL"


def test_format_kiwoom_code_unknown_exchange_no_suffix() -> None:
    assert format_kiwoom_code("000660", "unknown") == "000660"


def test_format_kiwoom_code_case_insensitive() -> None:
    assert format_kiwoom_code("000660", "NXT") == "000660_NX"
    assert format_kiwoom_code("000660", "SOR") == "000660_AL"


# ---------------------------------------------------------------------------
# env-specific key selection
# ---------------------------------------------------------------------------


def test_load_kiwoom_api_config_mock_env_prefers_mock_key() -> None:
    config = load_kiwoom_api_config(
        {
            "KIWOOM_ENV": "mock",
            "INTRADAY_PROVIDER": "websocket",
            "KIWOOM_MOCK_APP_KEY": "mock-app",
            "KIWOOM_MOCK_SECRET_KEY": "mock-secret",
            "KIWOOM_APP_KEY": "legacy-app",
            "KIWOOM_SECRET_KEY": "legacy-secret",
        },
        load_env_file=False,
    )

    assert config.app_key == "mock-app"
    assert config.secret_key == "mock-secret"


def test_load_kiwoom_api_config_mock_env_falls_back_to_legacy_key() -> None:
    config = load_kiwoom_api_config(
        {
            "KIWOOM_ENV": "mock",
            "INTRADAY_PROVIDER": "websocket",
            "KIWOOM_APP_KEY": "legacy-app",
            "KIWOOM_APP_SECRET": "legacy-secret",
        },
        load_env_file=False,
    )

    assert config.app_key == "legacy-app"
    assert config.secret_key == "legacy-secret"


def test_load_kiwoom_api_config_real_env_rejects_missing_real_key() -> None:
    with pytest.raises(KiwoomAuthError, match="KIWOOM_REAL_APP_KEY"):
        load_kiwoom_api_config(
            {
                "KIWOOM_ENV": "real",
                "INTRADAY_PROVIDER": "websocket",
                "KIWOOM_APP_KEY": "mock-only-key",   # should NOT be used for real
            },
            load_env_file=False,
        )


def test_load_kiwoom_api_config_real_env_rejects_missing_real_secret() -> None:
    with pytest.raises(KiwoomAuthError, match="KIWOOM_REAL_SECRET_KEY"):
        load_kiwoom_api_config(
            {
                "KIWOOM_ENV": "real",
                "INTRADAY_PROVIDER": "websocket",
                "KIWOOM_REAL_APP_KEY": "real-app",
                # KIWOOM_REAL_SECRET_KEY intentionally omitted
            },
            load_env_file=False,
        )


# ---------------------------------------------------------------------------
# kiwoom_env prod alias
# ---------------------------------------------------------------------------


def test_load_kiwoom_api_config_prod_alias_resolves_to_real_hosts() -> None:
    config = load_kiwoom_api_config(
        {
            "KIWOOM_ENV": "prod",
            "INTRADAY_PROVIDER": "websocket",
            "KIWOOM_REAL_APP_KEY": "real-app",
            "KIWOOM_REAL_SECRET_KEY": "real-secret",
        },
        load_env_file=False,
    )

    assert config.env == "real"
    assert config.rest_host == REAL_REST_HOST
    assert config.ws_url == REAL_WS_URL
    assert config.app_key == "real-app"


# ---------------------------------------------------------------------------
# normalize_tick_message — extended fields
# ---------------------------------------------------------------------------


def test_normalize_tick_message_extracts_item_and_type() -> None:
    raw = json.dumps({
        "trnm": "REAL",
        "data": [{"item": "000660", "type": "0B", "name": "SK하이닉스"}],
    })

    result = normalize_tick_message(raw)

    assert result["item"] == "000660"
    assert result["type"] == "0B"
    assert result["name"] == "SK하이닉스"
    assert result["raw"] == raw


def test_normalize_tick_message_returns_none_for_missing_fields() -> None:
    raw = json.dumps({"trnm": "REAL", "data": [{}]})

    result = normalize_tick_message(raw)

    assert result["item"] is None
    assert result["current_price"] is None
    assert result["trade_volume"] is None
    assert result["trade_time"] is None  # was execution_time in old placeholder


# ---------------------------------------------------------------------------
# parse_item_code — KRX / NXT / SOR splitting (confirmed prod 2026-06-01)
# ---------------------------------------------------------------------------


def test_parse_item_code_krx_plain() -> None:
    result = parse_item_code("000660")
    assert result == {"raw_code": "000660", "base_code": "000660", "exchange": "krx"}


def test_parse_item_code_nxt_suffix() -> None:
    result = parse_item_code("000660_NX")
    assert result == {"raw_code": "000660_NX", "base_code": "000660", "exchange": "nxt"}


def test_parse_item_code_sor_suffix() -> None:
    result = parse_item_code("000660_AL")
    assert result == {"raw_code": "000660_AL", "base_code": "000660", "exchange": "sor"}


def test_parse_item_code_case_insensitive_suffix() -> None:
    # Kiwoom server returns uppercase suffixes; tolerate lowercase too
    assert parse_item_code("000660_nx")["exchange"] == "nxt"
    assert parse_item_code("000660_al")["exchange"] == "sor"


def test_parse_item_code_samsung_krx() -> None:
    result = parse_item_code("005930")
    assert result["base_code"] == "005930"
    assert result["exchange"] == "krx"


# ---------------------------------------------------------------------------
# parse_signed_int / parse_signed_float
# ---------------------------------------------------------------------------


def test_parse_signed_int_positive_sign() -> None:
    assert parse_signed_int("+2380000") == 2380000


def test_parse_signed_int_negative_sign() -> None:
    assert parse_signed_int("-10") == -10


def test_parse_signed_int_plain_string() -> None:
    assert parse_signed_int("1000") == 1000


def test_parse_signed_int_empty_string() -> None:
    assert parse_signed_int("") is None


def test_parse_signed_int_none() -> None:
    assert parse_signed_int(None) is None


def test_parse_signed_int_non_numeric() -> None:
    assert parse_signed_int("abc") is None


def test_parse_signed_float_positive() -> None:
    assert parse_signed_float("+0.70") == pytest.approx(0.70)


def test_parse_signed_float_negative() -> None:
    assert parse_signed_float("-1.23") == pytest.approx(-1.23)


def test_parse_signed_float_none() -> None:
    assert parse_signed_float(None) is None


def test_parse_signed_float_empty() -> None:
    assert parse_signed_float("") is None


# ---------------------------------------------------------------------------
# normalize_tick_rows — per-row processing, multi-row separation
# ---------------------------------------------------------------------------


def _make_0b_entry(item: str, **overrides: str) -> dict:
    """Build a minimal type-0B data entry with confirmed field indices."""
    base = {
        "item": item,
        "type": "0B",
        "name": "주식체결",
        "20": "134500",    # trade_time
        "10": "+72000",    # current_price
        "11": "+500",      # change_price
        "12": "+0.70",     # change_rate
        "15": "1500",      # trade_volume
        "13": "3000000",   # accumulated_volume
        "14": "216000000000",  # accumulated_trade_value
    }
    base.update(overrides)
    return base


def test_normalize_tick_rows_krx_single_row() -> None:
    payload = json.dumps({
        "trnm": "REAL",
        "data": [_make_0b_entry("000660")],
    })

    rows = normalize_tick_rows(payload)

    assert len(rows) == 1
    r = rows[0]
    assert r["item"] == "000660"
    assert r["base_code"] == "000660"
    assert r["exchange"] == "krx"
    assert r["trade_time"] == "134500"
    assert r["current_price"] == 72000
    assert r["change_price"] == 500
    assert r["change_rate"] == pytest.approx(0.70)
    assert r["trade_volume"] == 1500
    assert r["accumulated_volume"] == 3000000
    assert r["accumulated_trade_value"] == 216000000000


def test_normalize_tick_rows_nxt_item_splits_correctly() -> None:
    payload = json.dumps({
        "trnm": "REAL",
        "data": [_make_0b_entry("000660_NX", **{"10": "+71800"})],
    })

    rows = normalize_tick_rows(payload)

    assert len(rows) == 1
    r = rows[0]
    assert r["item"] == "000660_NX"
    assert r["base_code"] == "000660"
    assert r["exchange"] == "nxt"
    assert r["current_price"] == 71800


def test_normalize_tick_rows_sor_item_splits_correctly() -> None:
    payload = json.dumps({
        "trnm": "REAL",
        "data": [_make_0b_entry("000660_AL", **{"10": "+71900"})],
    })

    rows = normalize_tick_rows(payload)

    r = rows[0]
    assert r["base_code"] == "000660"
    assert r["exchange"] == "sor"
    assert r["current_price"] == 71900


def test_normalize_tick_rows_multi_row_returns_separate_entries() -> None:
    """Multi-row payloads produce one dict per row — no duplication."""
    payload = json.dumps({
        "trnm": "REAL",
        "data": [
            _make_0b_entry("005930", **{"10": "+55000", "15": "2000"}),
            _make_0b_entry("000660", **{"10": "+72000", "15": "1500"}),
        ],
    })

    rows = normalize_tick_rows(payload)

    assert len(rows) == 2
    assert rows[0]["item"] == "005930"
    assert rows[0]["current_price"] == 55000
    assert rows[0]["trade_volume"] == 2000
    assert rows[1]["item"] == "000660"
    assert rows[1]["current_price"] == 72000
    assert rows[1]["trade_volume"] == 1500


def test_normalize_tick_rows_non_dict_entries_are_skipped() -> None:
    """List entries (not dicts) in data are skipped without error."""
    payload = json.dumps({
        "trnm": "REAL",
        "data": [["005930"], ["000660"]],
    })

    rows = normalize_tick_rows(payload)

    assert rows == []


def test_normalize_tick_rows_best_ask_bid_are_none_until_confirmed() -> None:
    """best_ask and best_bid are None until their field indices are confirmed."""
    payload = json.dumps({
        "trnm": "REAL",
        "data": [_make_0b_entry("000660")],
    })

    rows = normalize_tick_rows(payload)

    assert rows[0]["best_ask"] is None
    assert rows[0]["best_bid"] is None


def test_normalize_tick_message_backward_compat_raw_preserved() -> None:
    """normalize_tick_message still returns raw and parsed for backward compat."""
    raw = json.dumps({"trnm": "REAL", "data": [_make_0b_entry("000660")]})

    result = normalize_tick_message(raw)

    assert result["raw"] == raw
    assert isinstance(result["parsed"], dict)
    assert result["item"] == "000660"
    assert result["base_code"] == "000660"
    assert result["exchange"] == "krx"
