from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv
import requests


class KiwoomAuthError(RuntimeError):
    """Raised when Kiwoom OAuth token issuance fails."""


MOCK_REST_HOST = "https://mockapi.kiwoom.com"
REAL_REST_HOST = "https://api.kiwoom.com"
MOCK_WS_URL = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
REAL_WS_URL = "wss://api.kiwoom.com:10000/api/dostk/websocket"


@dataclass(frozen=True)
class AccessToken:
    token: str
    token_type: str
    expires_dt: str


@dataclass(frozen=True)
class KiwoomApiConfig:
    env: str
    provider: str
    rest_host: str
    ws_url: str
    app_key: str
    secret_key: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_project_env() -> None:
    load_dotenv(_project_root() / ".env")


def _normalized_env(value: str | None) -> str:
    normalized = (value or "mock").strip().lower()
    if normalized == "prod":
        normalized = "real"
    if normalized not in {"mock", "real"}:
        raise KiwoomAuthError("KIWOOM_ENV must be 'mock', 'real', or 'prod' (alias for real).")
    return normalized


def _normalized_provider(value: str | None) -> str:
    normalized = (value or "mock").strip().lower()
    if normalized not in {"mock", "rest", "websocket"}:
        raise KiwoomAuthError("INTRADAY_PROVIDER must be one of: mock, rest, websocket.")
    return normalized


def _select_app_key(env_map: Mapping[str, str], env: str) -> str:
    """Return the correct app key for the given environment.

    mock: KIWOOM_MOCK_APP_KEY preferred; falls back to KIWOOM_APP_KEY (legacy).
    real: KIWOOM_REAL_APP_KEY required; no fallback to avoid env mismatch (error 8030).
    """
    if env == "mock":
        return (
            str(env_map.get("KIWOOM_MOCK_APP_KEY") or env_map.get("KIWOOM_APP_KEY") or "").strip()
        )
    # real / prod
    key = str(env_map.get("KIWOOM_REAL_APP_KEY") or "").strip()
    if not key:
        raise KiwoomAuthError(
            "KIWOOM_REAL_APP_KEY is required when KIWOOM_ENV=real/prod. "
            "Set a real-investment app key. "
            "Do not use a mock/simulated key with the prod server — "
            "it will be rejected with error 8030 (investment type mismatch)."
        )
    return key


def _select_secret_key(env_map: Mapping[str, str], env: str) -> str:
    """Return the correct secret key for the given environment.

    mock: KIWOOM_MOCK_SECRET_KEY preferred; falls back to KIWOOM_SECRET_KEY /
          KIWOOM_APP_SECRET (legacy aliases).
    real: KIWOOM_REAL_SECRET_KEY required; no fallback to avoid env mismatch (error 8030).
    """
    if env == "mock":
        return str(
            env_map.get("KIWOOM_MOCK_SECRET_KEY")
            or env_map.get("KIWOOM_SECRET_KEY")
            or env_map.get("KIWOOM_APP_SECRET")
            or ""
        ).strip()
    # real / prod
    key = str(env_map.get("KIWOOM_REAL_SECRET_KEY") or "").strip()
    if not key:
        raise KiwoomAuthError(
            "KIWOOM_REAL_SECRET_KEY is required when KIWOOM_ENV=real/prod. "
            "Set a real-investment secret key. "
            "Do not use a mock/simulated key with the prod server — "
            "it will be rejected with error 8030 (investment type mismatch)."
        )
    return key


def load_kiwoom_api_config(
    environ: Mapping[str, str] | None = None,
    *,
    load_env_file: bool = True,
) -> KiwoomApiConfig:
    """Load non-trading Kiwoom market-data connection settings from env.

    Key selection per environment:
      mock  -> KIWOOM_MOCK_APP_KEY / KIWOOM_MOCK_SECRET_KEY
               (fallback: legacy KIWOOM_APP_KEY / KIWOOM_SECRET_KEY)
      real  -> KIWOOM_REAL_APP_KEY / KIWOOM_REAL_SECRET_KEY  (required, no fallback)
      prod  -> alias for real

    Using a mock/simulated key against the real server causes Kiwoom error 8030
    (investment type mismatch). Using a real key against the mock server also
    triggers 8030. Keeping the keys separated prevents this.

    This helper intentionally exposes only market-data hosts and credentials.
    It does not read account numbers and does not configure order endpoints.
    """
    if environ is None and load_env_file:
        _load_project_env()
    env_map = environ if environ is not None else os.environ
    env = _normalized_env(env_map.get("KIWOOM_ENV"))
    provider = _normalized_provider(env_map.get("INTRADAY_PROVIDER"))
    rest_host = MOCK_REST_HOST if env == "mock" else REAL_REST_HOST
    ws_url = MOCK_WS_URL if env == "mock" else REAL_WS_URL
    return KiwoomApiConfig(
        env=env,
        provider=provider,
        rest_host=rest_host,
        ws_url=ws_url,
        app_key=_select_app_key(env_map, env),
        secret_key=_select_secret_key(env_map, env),
    )


def issue_access_token(base_url: str, app_key: str, secret_key: str, timeout: float = 10.0) -> AccessToken:
    if not app_key or not secret_key:
        raise KiwoomAuthError(
            "App key and secret key are required for Kiwoom API access. "
            "For mock env set KIWOOM_MOCK_APP_KEY / KIWOOM_MOCK_SECRET_KEY; "
            "for real/prod env set KIWOOM_REAL_APP_KEY / KIWOOM_REAL_SECRET_KEY."
        )

    response = requests.post(
        f"{base_url.rstrip('/')}/oauth2/token",
        headers={"Content-Type": "application/json;charset=UTF-8"},
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": secret_key,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("return_code") not in (None, 0):
        return_code = payload.get("return_code")
        return_msg = str(payload.get("return_msg") or "Kiwoom token request failed.")
        if return_code == 8030 or "8030" in return_msg:
            raise KiwoomAuthError(
                f"{return_msg} "
                "App key investment type does not match the selected Kiwoom environment. "
                "mock key cannot be used with prod server; "
                "real key cannot be used with mock server. "
                "Check KIWOOM_ENV and use KIWOOM_MOCK_APP_KEY for mock "
                "or KIWOOM_REAL_APP_KEY for real/prod."
            )
        raise KiwoomAuthError(return_msg)

    try:
        return AccessToken(
            token=str(payload["token"]),
            token_type=str(payload.get("token_type", "bearer")),
            expires_dt=str(payload["expires_dt"]),
        )
    except KeyError as exc:
        raise KiwoomAuthError(f"Kiwoom token response is missing field: {exc}") from exc


def issue_access_token_from_env(timeout: float = 10.0) -> AccessToken:
    config = load_kiwoom_api_config()
    return issue_access_token(
        config.rest_host,
        config.app_key,
        config.secret_key,
        timeout=timeout,
    )
