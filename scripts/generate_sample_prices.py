from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEME_MAP_PATH = PROJECT_ROOT / "data" / "theme_map.csv"
SAMPLE_PRICES_PATH = PROJECT_ROOT / "data" / "sample_prices.csv"


SECTOR_BIAS = {
    "MLCC": 12.5,
    "전장부품": 9.0,
    "반도체": 6.0,
    "HBM": 8.2,
    "AI반도체": 5.4,
    "방산": 4.3,
    "우주항공": 3.8,
    "조선": 3.4,
    "전력설비": 3.0,
    "원전": 2.7,
    "로봇": 2.3,
    "2차전지": 1.4,
    "자동차": 0.8,
    "금융": 0.4,
    "바이오": -0.6,
    "인터넷": -1.1,
}


def _stable_seed(text: str) -> int:
    value = 0
    for char in text:
        value = (value * 31 + ord(char)) % 10_000
    return value


def _change_rate(row: dict[str, str]) -> float:
    themes = [row.get("theme1", ""), row.get("theme2", ""), row.get("theme3", "")]
    base = max((SECTOR_BIAS.get(theme, -0.2) for theme in themes), default=-0.2)
    jitter = (_stable_seed(row["code"]) % 240) / 100 - 1.2
    return round(base + jitter, 2)


def _price_for(code: str) -> int:
    seed = _stable_seed(code)
    return int((18_000 + seed * 23) // 100 * 100)


def main() -> None:
    with THEME_MAP_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    output_rows = []
    for row in rows:
        code = row["code"].zfill(6)
        current_price = _price_for(code)
        change_rate = _change_rate(row)
        open_price = int(current_price / (1 + change_rate / 100)) if change_rate > -99 else current_price
        volume = 80_000 + (_stable_seed(row["name"]) % 4_500_000)
        trade_value = current_price * volume
        output_rows.append(
            {
                "code": code,
                "name": row["name"],
                "change_rate": change_rate,
                "trade_value": trade_value,
                "volume": volume,
                "open_price": open_price,
                "current_price": current_price,
            }
        )

    with SAMPLE_PRICES_PATH.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "code",
                "name",
                "change_rate",
                "trade_value",
                "volume",
                "open_price",
                "current_price",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)


if __name__ == "__main__":
    main()
