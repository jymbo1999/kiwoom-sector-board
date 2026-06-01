from __future__ import annotations

from src.config import (
    get_naver_credentials,
    get_openai_api_key,
    get_opendart_api_key,
    load_settings,
)


def test_load_settings_supports_render_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_APP_KEY", "app-key")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "app-secret")
    monkeypatch.setenv("USE_DUMMY_DATA", "false")
    monkeypatch.delenv("KIWOOM_SECRET_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_USE_MOCK", raising=False)
    # Remove KIWOOM_ENV so the test exercises the USE_DUMMY_DATA fallback path.
    monkeypatch.delenv("KIWOOM_ENV", raising=False)

    settings = load_settings()

    assert settings.app_key == "app-key"
    assert settings.secret_key == "app-secret"
    assert settings.use_mock is False


def test_load_settings_preserves_legacy_env_names(monkeypatch) -> None:
    monkeypatch.delenv("KIWOOM_APP_SECRET", raising=False)
    monkeypatch.delenv("USE_DUMMY_DATA", raising=False)
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "legacy-secret")
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")

    settings = load_settings()

    assert settings.secret_key == "legacy-secret"
    assert settings.use_mock is True


def test_load_settings_has_safe_intraday_defaults(monkeypatch) -> None:
    for key in [
        "INTRADAY_BOARD_ENABLED",
        "INTRADAY_PROVIDER",
        "INTRADAY_POLL_SECONDS",
        "INTRADAY_MAX_CODES",
        "UNIVERSE_MIN_MARKET_CAP",
        "UNIVERSE_MIN_TRADE_VALUE",
        "INTRADAY_EVIDENCE_ENABLED",
        "INTRADAY_EVIDENCE_LIMIT",
        "KIWOOM_ENV",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.intraday_board_enabled is False
    assert settings.intraday_provider == "mock"
    assert settings.intraday_poll_seconds == 60
    assert settings.intraday_max_codes == 300
    assert settings.universe_min_market_cap == 500_000_000_000
    assert settings.universe_min_trade_value == 0
    assert settings.intraday_evidence_enabled is False
    assert settings.intraday_evidence_limit == 10
    assert settings.kiwoom_env == "mock"


# ---------------------------------------------------------------------------
# KIWOOM_ENV priority over KIWOOM_USE_MOCK / USE_DUMMY_DATA
# ---------------------------------------------------------------------------


def test_kiwoom_env_mock_wins_over_use_mock_false(monkeypatch) -> None:
    """KIWOOM_ENV=mock forces use_mock=True and mockapi URL even if KIWOOM_USE_MOCK=false."""
    monkeypatch.setenv("KIWOOM_ENV", "mock")
    monkeypatch.setenv("KIWOOM_USE_MOCK", "false")
    monkeypatch.delenv("KIWOOM_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.use_mock is True
    assert "mockapi.kiwoom.com" in settings.base_url


def test_kiwoom_env_real_wins_over_use_mock_true(monkeypatch) -> None:
    """KIWOOM_ENV=real forces use_mock=False and real URL even if KIWOOM_USE_MOCK=true."""
    monkeypatch.setenv("KIWOOM_ENV", "real")
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")
    monkeypatch.delenv("KIWOOM_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.use_mock is False
    assert "api.kiwoom.com" in settings.base_url
    assert "mockapi" not in settings.base_url


def test_kiwoom_env_prod_alias_uses_real_url(monkeypatch) -> None:
    """KIWOOM_ENV=prod (alias for real) must never select mockapi.kiwoom.com."""
    monkeypatch.setenv("KIWOOM_ENV", "prod")
    monkeypatch.setenv("KIWOOM_USE_MOCK", "true")  # should be ignored
    monkeypatch.delenv("KIWOOM_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.use_mock is False
    assert "api.kiwoom.com" in settings.base_url
    assert "mockapi" not in settings.base_url


def test_kiwoom_base_url_manual_override_is_respected(monkeypatch) -> None:
    """KIWOOM_BASE_URL overrides the KIWOOM_ENV-derived URL when explicitly set."""
    monkeypatch.setenv("KIWOOM_ENV", "real")
    monkeypatch.setenv("KIWOOM_BASE_URL", "https://custom.kiwoom.example.com")

    settings = load_settings()

    assert settings.base_url == "https://custom.kiwoom.example.com"


def test_kiwoom_env_absent_falls_back_to_use_mock(monkeypatch) -> None:
    """When KIWOOM_ENV is absent, KIWOOM_USE_MOCK is still respected (backward compat)."""
    monkeypatch.delenv("KIWOOM_ENV", raising=False)
    monkeypatch.setenv("KIWOOM_USE_MOCK", "false")
    monkeypatch.delenv("KIWOOM_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.use_mock is False
    assert "mockapi" not in settings.base_url


# ---------------------------------------------------------------------------
# API key helper smoke tests
# ---------------------------------------------------------------------------

def test_get_opendart_api_key_returns_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    assert get_opendart_api_key() == ""


def test_get_opendart_api_key_returns_value_when_set(monkeypatch) -> None:
    monkeypatch.setenv("OPENDART_API_KEY", "dart-test-key")
    assert get_opendart_api_key() == "dart-test-key"


def test_get_naver_credentials_returns_empty_tuple_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    client_id, client_secret = get_naver_credentials()
    assert client_id == ""
    assert client_secret == ""


def test_get_naver_credentials_returns_values_when_set(monkeypatch) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver-secret")
    client_id, client_secret = get_naver_credentials()
    assert client_id == "naver-id"
    assert client_secret == "naver-secret"


def test_get_openai_api_key_returns_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_openai_api_key() == ""


def test_get_openai_api_key_returns_value_when_set(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert get_openai_api_key() == "sk-test"
