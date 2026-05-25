from __future__ import annotations

import pandas as pd

from src.theme_loader import themes_to_long


def test_themes_to_long_removes_empty_values() -> None:
    theme_map = pd.DataFrame(
        [
            {"code": "005930", "name": "삼성전자", "theme1": "반도체", "theme2": "", "theme3": None},
            {"code": "000660", "name": "SK하이닉스", "theme1": "반도체", "theme2": "HBM", "theme3": "메모리"},
        ]
    )

    result = themes_to_long(theme_map)

    assert set(result["sector"]) == {"반도체", "HBM", "메모리"}
    assert len(result) == 4
