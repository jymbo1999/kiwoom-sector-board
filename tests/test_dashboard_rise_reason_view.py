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
            "reason_summary_ko": "관련 네이버 뉴스가 충분히 확인되지 않았습니다.",
            "confidence": "unknown",
            "evidence_titles": ["근거1", "근거2", "근거3", "근거4"],
            "caveat": "주가 흐름과 직접 연결된 뉴스 snippet이 부족해 요약 범위를 제한했습니다.",
        }
    ])

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "삼성전자"
    assert row["ticker"] == "005930"
    assert row["pct_change_value"] == 3.2
    assert row["pct_change"] == "+3.20%"
    assert row["sector"] == "반도체"
    assert row["confidence"] == "unknown"
    assert row["caveat"] == "주가 흐름과 직접 연결된 뉴스 snippet이 부족해 요약 범위를 제한했습니다."
    # evidence_items_ui: empty since no evidence_items_ui key in input
    assert row["evidence_items_ui"] == []
    # fallback titles come from evidence_titles, capped at 5
    assert row["evidence_titles_fallback"] == ["근거1", "근거2", "근거3", "근거4"]


def test_rise_reason_rows_uses_evidence_items_ui_when_present() -> None:
    ui_items = [
        {"title": "SK하이닉스 주가 강세", "url": "https://news.naver.com/1", "excerpt": "요약1", "provider": "Naver", "published_at": "2025-05-20T00:00:00", "source_type": "news"},
        {"title": "SK하이닉스 HBM 기대감", "url": "https://news.naver.com/2", "excerpt": "요약2", "provider": "Naver", "published_at": "2025-05-20T10:00:00", "source_type": "news"},
    ]
    rows = _rise_reason_rows([
        {
            "ticker": "000660",
            "name": "SK하이닉스",
            "market_move": {"pct_change": 8.7, "sector": "반도체"},
            "reason_summary_ko": "관련 뉴스 요약",
            "confidence": "high",
            "evidence_titles": ["SK하이닉스 주가 강세", "SK하이닉스 HBM 기대감"],
            "evidence_items_ui": ui_items,
            "caveat": "투자 권유 아님",
        }
    ])

    row = rows[0]
    assert row["evidence_items_ui"] == ui_items
    assert row["evidence_titles_fallback"] == ["SK하이닉스 주가 강세", "SK하이닉스 HBM 기대감"]
