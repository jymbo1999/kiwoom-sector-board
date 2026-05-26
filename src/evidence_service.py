from __future__ import annotations

from datetime import date
from typing import Any

from .market_data import get_market_movers
from .news_service import build_news_queries_for_mover, search_naver_news


EVIDENCE_KEYS = [
    "source_type",
    "provider",
    "title",
    "published_at",
    "url",
    "excerpt",
    "weight",
    "relevance_score",
    "matched_terms",
]


def _trade_date_value(trade_date: str | date | None) -> str:
    if trade_date is None:
        return date.today().isoformat()
    if isinstance(trade_date, date):
        return trade_date.isoformat()
    return str(trade_date)


def _safe_evidence_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    safe_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = {
            "source_type": str(item.get("source_type", "")),
            "provider": str(item.get("provider", "")),
            "title": str(item.get("title", "")),
            "published_at": str(item.get("published_at", "")),
            "url": str(item.get("url", "")),
            "excerpt": str(item.get("excerpt", "")),
            "weight": float(item.get("weight", 0.0) or 0.0),
            "relevance_score": float(item.get("relevance_score", 0.0) or 0.0),
            "matched_terms": [
                str(term)
                for term in item.get("matched_terms", [])
                if str(term).strip()
            ][:10] if isinstance(item.get("matched_terms", []), list) else [],
        }
        safe_items.append({key: normalized[key] for key in EVIDENCE_KEYS})
    return safe_items


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []

    for item in items:
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        unique.append(item)
    return unique


def _sort_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            float(item.get("relevance_score", 0.0) or 0.0),
            float(item.get("weight", 0.0) or 0.0),
            str(item.get("published_at", "")),
        ),
        reverse=True,
    )


def _collect_evidence(mover: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(mover.get("name", ""))
    evidence: list[dict[str, Any]] = []

    try:
        for query in build_news_queries_for_mover(mover)[:5]:
            evidence.extend(_safe_evidence_items(search_naver_news(query, display=10, stock_name=name)))
    except Exception:
        pass

    return _sort_evidence(_dedupe_evidence(evidence))


def build_evidence_bundle(mover: dict[str, Any], trade_date: str | date | None = None) -> dict[str, Any]:
    """Build one market-move evidence bundle without GPT summarization."""

    evidence = _collect_evidence(mover)
    return {
        "trade_date": _trade_date_value(trade_date),
        "ticker": str(mover.get("ticker", "")),
        "name": str(mover.get("name", "")),
        "market": str(mover.get("market", "")),
        "market_move": {
            "pct_change": float(mover.get("pct_change", 0.0) or 0.0),
            "volume_rank": int(mover.get("volume_rank", 0) or 0),
            "sector": str(mover.get("sector", "")),
            "trading_value": int(mover.get("trading_value", 0) or 0),
        },
        "evidence": evidence,
    }


def build_evidence_bundles(date: str | date | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Build evidence bundles for the current market mover candidates."""

    try:
        movers = get_market_movers(date=date, limit=limit)
    except Exception:
        movers = []
    return [
        build_evidence_bundle(mover, trade_date=date)
        for mover in movers
        if isinstance(mover, dict)
    ]
