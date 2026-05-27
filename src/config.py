from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# When installed as a pip package, data files live in src/data/ (package data).
# When run from the repo root (development), fall back to the top-level data/ directory.
_pkg_data_dir = Path(__file__).resolve().parent / "data"
DATA_DIR = _pkg_data_dir if _pkg_data_dir.exists() else PROJECT_ROOT / "data"

# Load .env once at import time so all modules share the same environment.
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_key: str
    secret_key: str
    base_url: str
    account_no: str
    use_mock: bool
    theme_map_path: Path
    sample_prices_path: Path
    morning_board_max_codes: int = 40
    api_timeout_seconds: float = 10.0
    api_retry_count: int = 2
    api_request_interval_seconds: float = 0.35
    # KRX 전체 종목 수집 모드 (pykrx 기반, Kiwoom API 불필요)
    use_krx_data: bool = True
    # KRX 수집 실행 시각 (KST 기준 시)
    krx_collect_hour: int = 4


def load_settings() -> Settings:
    # KIWOOM_USE_MOCK takes highest priority when explicitly set; fall back to USE_DUMMY_DATA.
    _kiwoom_use_mock = os.getenv("KIWOOM_USE_MOCK")
    if _kiwoom_use_mock is not None:
        use_mock = _as_bool(_kiwoom_use_mock)
    else:
        use_mock = _as_bool(os.getenv("USE_DUMMY_DATA"), default=True)
    base_url = os.getenv("KIWOOM_BASE_URL") or (
        "https://mockapi.kiwoom.com" if use_mock else "https://api.kiwoom.com"
    )

    # KRX 모드: 명시적으로 비활성화(USE_KRX_DATA=false)하지 않으면 기본 True
    _use_krx_env = os.getenv("USE_KRX_DATA")
    if _use_krx_env is not None:
        use_krx_data = _as_bool(_use_krx_env)
    else:
        use_krx_data = True

    return Settings(
        app_key=os.getenv("KIWOOM_APP_KEY", ""),
        secret_key=os.getenv("KIWOOM_APP_SECRET", os.getenv("KIWOOM_SECRET_KEY", "")),
        base_url=base_url.rstrip("/"),
        account_no=os.getenv("KIWOOM_ACCOUNT_NO", ""),
        use_mock=use_mock,
        theme_map_path=DATA_DIR / "theme_map.csv",
        sample_prices_path=DATA_DIR / "sample_prices.csv",
        morning_board_max_codes=max(0, _as_int(os.getenv("MORNING_BOARD_MAX_CODES"), 60)),
        api_timeout_seconds=max(1.0, _as_float(os.getenv("KIWOOM_API_TIMEOUT_SECONDS"), 10.0)),
        api_retry_count=max(0, _as_int(os.getenv("KIWOOM_API_RETRY_COUNT"), 2)),
        api_request_interval_seconds=max(0.0, _as_float(os.getenv("KIWOOM_REQUEST_INTERVAL_SECONDS"), 0.35)),
        use_krx_data=use_krx_data,
        krx_collect_hour=max(0, min(23, _as_int(os.getenv("KRX_COLLECT_HOUR"), 4))),
    )


# ---------------------------------------------------------------------------
# External API key helpers — return empty string when key is absent so callers
# can treat a falsy value as "skip real API, use fallback".
# ---------------------------------------------------------------------------

def get_opendart_api_key() -> str:
    key = os.getenv("OPENDART_API_KEY", "")
    if not key:
        logger.debug("OPENDART_API_KEY not set — DART disclosures will be skipped")
    return key


def get_naver_credentials() -> tuple[str, str]:
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.debug("NAVER_CLIENT_ID/SECRET not set — Naver news will be skipped")
    return client_id, client_secret


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        logger.debug("OPENAI_API_KEY not set — rise reason will use fallback summary")
    return key
