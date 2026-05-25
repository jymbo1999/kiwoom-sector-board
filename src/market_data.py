from __future__ import annotations

import pandas as pd

from .config import Settings
from .dummy_data import load_sample_prices
from .kiwoom_client import KiwoomApiError, KiwoomRestClient


def load_market_prices(settings: Settings, codes: list[str]) -> tuple[pd.DataFrame, str | None, bool]:
    if settings.use_mock:
        return load_sample_prices(settings.sample_prices_path), None, True

    client = KiwoomRestClient(
        base_url=settings.base_url,
        app_key=settings.app_key,
        secret_key=settings.secret_key,
    )
    try:
        return client.fetch_current_prices(codes), None, False
    except KiwoomApiError as exc:
        fallback = load_sample_prices(settings.sample_prices_path)
        return fallback, f"키움 API 조회에 실패해 샘플 데이터로 화면을 표시합니다: {exc}", True
