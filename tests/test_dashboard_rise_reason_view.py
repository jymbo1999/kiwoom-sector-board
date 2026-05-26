from __future__ import annotations

from src.dashboard_components import _rise_reason_rows


def test_rise_reason_rows_formats_required_ui_columns() -> None:
    rows = _rise_reason_rows([
        {
            "ticker": "005930",
            "name": "삼성전자",
            "market_move": {
                "pct_change": 3.2,
                "sector": "반도체",
            },
            "reason_summary_ko": "현재 수집된 근거만으로 상승 원인을 확정하기 어렵습니다.",
            "confidence": "unknown",
            "evidence_titles": ["근거1", "근거2", "근거3", "근거4"],
            "caveat": "공시 또는 충분한 뉴스 근거가 확인되지 않아 추정하지 않았습니다.",
        }
    ])

    assert rows == [
        {
            "name": "삼성전자",
            "ticker": "005930",
            "pct_change": "+3.20%",
            "sector": "반도체",
            "reason_summary_ko": "현재 수집된 근거만으로 상승 원인을 확정하기 어렵습니다.",
            "confidence": "unknown",
            "evidence_titles": "근거1\n근거2\n근거3",
            "caveat": "공시 또는 충분한 뉴스 근거가 확인되지 않아 추정하지 않았습니다.",
        }
    ]
