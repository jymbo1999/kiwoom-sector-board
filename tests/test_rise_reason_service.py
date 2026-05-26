from __future__ import annotations

from src.rise_reason_service import ALLOWED_CONFIDENCE, SUMMARY_KEYS, summarize_rise_reason, summarize_rise_reasons


SAMPLE_BUNDLE = {
    "trade_date": "2026-05-26",
    "ticker": "005930",
    "name": "삼성전자",
    "market": "KOSPI",
    "market_move": {
        "pct_change": 3.2,
        "volume_rank": 1,
        "sector": "반도체",
        "trading_value": 123_456_789_000,
    },
    "evidence": [
        {
            "source_type": "news",
            "provider": "Naver",
            "title": "삼성전자, HBM 기대감에 상승",
            "published_at": "2026-05-26T08:30:00",
            "url": "https://example.com/a",
            "excerpt": "뉴스 API description/snippet",
            "weight": 0.5,
        },
        {
            "source_type": "dart",
            "provider": "OpenDART",
            "title": "단일판매 공급계약",
            "published_at": "2026-05-26T09:03:00",
            "url": "https://example.com/b",
            "excerpt": "공급계약 체결 관련 공시",
            "weight": 1.0,
        },
        {
            "source_type": "news",
            "provider": "Naver",
            "title": "삼성전자 실적 전망",
            "published_at": "2026-05-26T09:30:00",
            "url": "https://example.com/c",
            "excerpt": "실적 기대감",
            "weight": 0.5,
        },
        {
            "source_type": "news",
            "provider": "Naver",
            "title": "삼성전자 반도체 수급",
            "published_at": "2026-05-26T10:30:00",
            "url": "https://example.com/d",
            "excerpt": "수급 개선",
            "weight": 0.5,
        },
    ],
}


def test_summarize_rise_reason_without_api_key_returns_required_schema(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    summary = summarize_rise_reason(SAMPLE_BUNDLE)

    assert isinstance(summary, dict)
    assert list(summary.keys()) == SUMMARY_KEYS
    assert summary["ticker"] == "005930"
    assert summary["name"] == "삼성전자"
    assert summary["confidence"] in ALLOWED_CONFIDENCE
    assert len(summary["evidence_titles"]) <= 3


def test_summarize_rise_reason_without_evidence_returns_unknown(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bundle = {**SAMPLE_BUNDLE, "evidence": []}

    summary = summarize_rise_reason(bundle)

    assert summary["confidence"] == "unknown"
    assert summary["reason_tags"] == []
    assert summary["evidence_titles"] == []


def test_summarize_rise_reasons_returns_list(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    summaries = summarize_rise_reasons([SAMPLE_BUNDLE])

    assert isinstance(summaries, list)
    assert len(summaries) == 1
    assert list(summaries[0].keys()) == SUMMARY_KEYS
