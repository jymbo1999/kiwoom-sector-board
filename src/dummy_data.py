from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_PRICE_COLUMNS = [
    "code",
    "name",
    "change_rate",
    "trade_value",
    "volume",
    "open_price",
    "current_price",
]


def load_sample_prices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str})
    missing = set(REQUIRED_PRICE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"sample price data is missing columns: {sorted(missing)}")
    return df[REQUIRED_PRICE_COLUMNS].copy()
