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
