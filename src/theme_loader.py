from __future__ import annotations

from pathlib import Path

import pandas as pd


THEME_COLUMNS = ["theme1", "theme2", "theme3"]
REQUIRED_COLUMNS = ["code", "name", *THEME_COLUMNS]


def load_theme_map(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str})
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"theme map is missing columns: {sorted(missing)}")
    return df[REQUIRED_COLUMNS].copy()


def themes_to_long(theme_map: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_COLUMNS) - set(theme_map.columns)
    if missing:
        raise ValueError(f"theme map is missing columns: {sorted(missing)}")

    long_df = theme_map.melt(
        id_vars=["code", "name"],
        value_vars=THEME_COLUMNS,
        var_name="theme_slot",
        value_name="sector",
    )
    long_df["sector"] = long_df["sector"].astype("string").str.strip()
    long_df = long_df.dropna(subset=["sector"])
    long_df = long_df[long_df["sector"] != ""]
    return long_df[["code", "name", "sector"]].drop_duplicates().reset_index(drop=True)
