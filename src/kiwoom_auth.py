from __future__ import annotations

from dataclasses import dataclass

import requests


class KiwoomAuthError(RuntimeError):
    """Raised when Kiwoom OAuth token issuance fails."""


@dataclass(frozen=True)
class AccessToken:
    token: str
    token_type: str
    expires_dt: str


def issue_access_token(base_url: str, app_key: str, secret_key: str, timeout: float = 10.0) -> AccessToken:
    if not app_key or not secret_key:
        raise KiwoomAuthError("KIWOOM_APP_KEY and KIWOOM_SECRET_KEY are required for real API mode.")

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
        raise KiwoomAuthError(payload.get("return_msg", "Kiwoom token request failed."))

    try:
        return AccessToken(
            token=str(payload["token"]),
            token_type=str(payload.get("token_type", "bearer")),
            expires_dt=str(payload["expires_dt"]),
        )
    except KeyError as exc:
        raise KiwoomAuthError(f"Kiwoom token response is missing field: {exc}") from exc
