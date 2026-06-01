from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
import random
from typing import Protocol

from .kiwoom_auth import KiwoomApiConfig, issue_access_token, load_kiwoom_api_config
from .kiwoom_client import KiwoomRestClient
from .kiwoom_websocket import KiwoomRawMessage, KiwoomWebSocketClient


DEFAULT_TEST_CODES = ["005930", "000660"]


class RawMarketDataProvider(Protocol):
    mode: str

    async def collect_raw_messages(
        self,
        codes: list[str],
        *,
        max_messages: int = 5,
        listen_seconds: float = 20.0,
    ) -> list[KiwoomRawMessage]:
        ...


@dataclass(frozen=True)
class MockQuoteProvider:
    mode: str = "mock"

    async def collect_raw_messages(
        self,
        codes: list[str],
        *,
        max_messages: int = 5,
        listen_seconds: float = 20.0,
    ) -> list[KiwoomRawMessage]:
        del listen_seconds
        normalized_codes = [str(code).zfill(6) for code in codes if str(code).strip()]
        if not normalized_codes:
            normalized_codes = DEFAULT_TEST_CODES
        messages: list[KiwoomRawMessage] = []
        for index in range(max_messages):
            code = normalized_codes[index % len(normalized_codes)]
            payload = {
                "provider": "mock",
                "trnm": "REAL",
                "type": "0B",
                "code": code,
                "name": "삼성전자" if code == "005930" else "SK하이닉스" if code == "000660" else code,
                "current_price": 70000 + random.randint(-500, 500),
                "change_rate": round(random.uniform(-1.0, 3.0), 2),
                "trade_value": random.randint(50_000_000_000, 300_000_000_000),
                "received_at": datetime.now().isoformat(timespec="seconds"),
            }
            messages.append(
                KiwoomRawMessage(
                    raw=json.dumps(payload, ensure_ascii=False),
                    received_at=payload["received_at"],
                )
            )
            await asyncio.sleep(0)
        return messages


@dataclass(frozen=True)
class KiwoomRestQuoteProvider:
    config: KiwoomApiConfig
    timeout: float = 10.0
    mode: str = "rest"

    async def collect_raw_messages(
        self,
        codes: list[str],
        *,
        max_messages: int = 5,
        listen_seconds: float = 20.0,
    ) -> list[KiwoomRawMessage]:
        del listen_seconds
        token = issue_access_token(
            self.config.rest_host,
            self.config.app_key,
            self.config.secret_key,
            timeout=self.timeout,
        )
        client = KiwoomRestClient(
            base_url=self.config.rest_host,
            app_key=self.config.app_key,
            secret_key=self.config.secret_key,
            timeout=self.timeout,
            token=token,
        )
        selected_codes = [str(code).zfill(6) for code in codes if str(code).strip()][:max_messages]
        frame = await asyncio.to_thread(client.fetch_current_prices, selected_codes)
        timestamp = datetime.now().isoformat(timespec="seconds")
        return [
            KiwoomRawMessage(
                raw=json.dumps(row, ensure_ascii=False),
                received_at=timestamp,
            )
            for row in frame.to_dict(orient="records")
        ]


@dataclass(frozen=True)
class KiwoomWebSocketRawProvider:
    config: KiwoomApiConfig
    timeout: float = 10.0
    mode: str = "websocket"

    async def collect_raw_messages(
        self,
        codes: list[str],
        *,
        max_messages: int = 5,
        listen_seconds: float = 20.0,
    ) -> list[KiwoomRawMessage]:
        token = issue_access_token(
            self.config.rest_host,
            self.config.app_key,
            self.config.secret_key,
            timeout=self.timeout,
        )
        client = KiwoomWebSocketClient(
            self.config.ws_url,
            token,
            connect_timeout=self.timeout,
        )
        return await client.collect_raw_messages(
            codes,
            max_messages=max_messages,
            listen_seconds=listen_seconds,
        )


def build_raw_market_data_provider(
    config: KiwoomApiConfig | None = None,
) -> RawMarketDataProvider:
    active_config = config or load_kiwoom_api_config()
    if active_config.provider == "mock":
        return MockQuoteProvider()
    if active_config.provider == "rest":
        return KiwoomRestQuoteProvider(active_config)
    if active_config.provider == "websocket":
        return KiwoomWebSocketRawProvider(active_config)
    raise ValueError(f"Unsupported INTRADAY_PROVIDER: {active_config.provider}")
