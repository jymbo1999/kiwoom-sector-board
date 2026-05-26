from __future__ import annotations

from src.config import load_settings


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
