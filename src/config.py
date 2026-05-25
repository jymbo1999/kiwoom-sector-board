from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_key: str
    secret_key: str
    base_url: str
    account_no: str
    use_mock: bool
    theme_map_path: Path
    sample_prices_path: Path


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    use_mock = _as_bool(os.getenv("KIWOOM_USE_MOCK"), default=True)
    base_url = os.getenv("KIWOOM_BASE_URL") or (
        "https://mockapi.kiwoom.com" if use_mock else "https://api.kiwoom.com"
    )

    return Settings(
        app_key=os.getenv("KIWOOM_APP_KEY", ""),
        secret_key=os.getenv("KIWOOM_SECRET_KEY", ""),
        base_url=base_url.rstrip("/"),
        account_no=os.getenv("KIWOOM_ACCOUNT_NO", ""),
        use_mock=use_mock,
        theme_map_path=DATA_DIR / "theme_map.csv",
        sample_prices_path=DATA_DIR / "sample_prices.csv",
    )
