from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from .kiwoom_auth import AccessToken, issue_access_token


class KiwoomApiError(RuntimeError):
    """Raised when a Kiwoom REST market-data request fails."""


@dataclass
class KiwoomRestClient:
    base_url: str
    app_key: str
    secret_key: str
    timeout: float = 10.0
    retry_count: int = 2
    backoff_seconds: float = 0.35
    token: AccessToken | None = None

    def get_access_token(self) -> AccessToken:
        if self.token is None:
            self.token = issue_access_token(
                self.base_url,
                self.app_key,
                self.secret_key,
                timeout=self.timeout,
            )
        return self.token

    def _headers(self, api_id: str) -> dict[str, str]:
        token = self.get_access_token()
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token.token}",
            "api-id": api_id,
        }

    def _post(self, endpoint: str, api_id: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{endpoint}"
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(api_id),
                    json=body,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("return_code") not in (None, 0):
                    raise KiwoomApiError(payload.get("return_msg", f"Kiwoom API {api_id} failed."))
                return payload
            except (requests.RequestException, ValueError, KiwoomApiError) as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise KiwoomApiError(str(last_error)) from last_error

    def fetch_current_prices(self, codes: list[str]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for code in codes:
            # Official guide: ka10001 stock basic information, POST /api/dostk/stkinfo,
            # body {"stk_cd": "..."} with api-id header. Field names below are
            # adapter-normalized from Kiwoom's abbreviated response.
            payload = self._post("/api/dostk/stkinfo", "ka10001", {"stk_cd": code})
            rows.append(_normalize_ka10001(payload, fallback_code=code))
            time.sleep(self.backoff_seconds)
        return pd.DataFrame(rows)


def _to_number(value: Any) -> float:
    text = str(value or "0").replace(",", "").strip()
    if text.startswith("+"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return 0.0


def _normalize_ka10001(payload: dict[str, Any], fallback_code: str) -> dict[str, Any]:
    # TODO: Re-check all response field mappings against the downloaded Kiwoom
    # API spec before relying on real-money operational dashboards. This MVP is
    # 조회 전용 and intentionally fails loudly if essential fields are absent.
    required_any = {
        "code": ["stk_cd"],
        "name": ["stk_nm"],
        "current_price": ["cur_prc"],
        "change_rate": ["flu_rt"],
        "volume": ["trde_qty"],
    }
    normalized: dict[str, Any] = {}
    missing: list[str] = []
    for target, candidates in required_any.items():
        value = next((payload.get(candidate) for candidate in candidates if candidate in payload), None)
        if value is None:
            missing.append(target)
        normalized[target] = value

    if missing:
        raise KiwoomApiError(f"ka10001 response missing required normalized fields: {missing}")

    current_price = abs(_to_number(normalized["current_price"]))
    volume = _to_number(normalized["volume"])
    trade_value = _to_number(payload.get("trde_prica") or payload.get("mac"))
    if trade_value == 0 and current_price and volume:
        trade_value = current_price * volume

    return {
        "code": str(normalized["code"] or fallback_code).zfill(6),
        "name": str(normalized["name"]),
        "change_rate": _to_number(normalized["change_rate"]),
        "trade_value": trade_value,
        "volume": volume,
        "open_price": abs(_to_number(payload.get("open_pric") or payload.get("open_price") or current_price)),
        "current_price": current_price,
    }
