from __future__ import annotations

from email.utils import parsedate_to_datetime
from html import unescape
import re
from typing import Any

import requests

from src.config import get_naver_credentials


NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
NEWS_WEIGHT = 0.5
PRICE_CONTEXT_KEYWORDS = [
    "주가",
    "상승",
    "급등",
    "강세",
    "반등",
    "신고가",
    "오름세",
    "상한가",
    "랠리",
]
REASON_CONTEXT_KEYWORDS = [
    "실적",
    "영업이익",
    "매출",
    "수주",
    "계약",
    "공급",
    "정책",
    "지원",
    "목표가",
    "증권가",
    "전망",
    "기대",
    "기대감",
    "수혜",
    "호조",
    "투자",
    "HBM",
    "AI",
    "방산",
    "로봇",
]
HARD_EXCLUDE_KEYWORDS = [
    "ETF",
    "ETN",
    "레버리지",
    "인버스",
    "선물",
    "계좌 인증",
    "수익률 인증",
    "하락",
    "약세",
    "급락",
    "내림세",
    "울고",
]
SOFT_EXCLUDE_KEYWORDS = [
    "코스피",
    "코스닥",
    "뉴욕증시",
    "환율",
    "물가",
    "지수",
    "마감",
    "장중",
]


def strip_html(value: str | None) -> str:
    """Remove simple HTML tags and decode entities from Naver search snippets."""

    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", "", value)
    return unescape(without_tags).strip()


def _normalize_pub_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return strip_html(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat(timespec="seconds")


def _build_news_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": "news",
        "provider": "Naver",
        "title": strip_html(str(item.get("title", ""))),
        "published_at": _normalize_pub_date(item.get("pubDate")),
        "url": str(item.get("originallink") or item.get("link") or ""),
        "excerpt": strip_html(str(item.get("description", ""))),
        "weight": NEWS_WEIGHT,
    }


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _matched_terms(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def _score_stock_news(item: dict[str, Any], stock_name: str | None = None) -> tuple[float, list[str], str]:
    title = str(item.get("title", ""))
    excerpt = str(item.get("excerpt", ""))
    text = f"{title} {excerpt}"
    compact_title = _compact_text(title)
    compact_text = _compact_text(text)
    compact_name = _compact_text(str(stock_name or ""))

    if compact_name and compact_name not in compact_text:
        return 0.0, [], "missing_stock_name"
    if compact_name and compact_name not in compact_title:
        return 0.0, [], "missing_stock_name_in_title"

    hard_excludes = _matched_terms(text, HARD_EXCLUDE_KEYWORDS)
    if hard_excludes:
        return 0.0, hard_excludes, "excluded_market_product"

    price_terms = _matched_terms(text, PRICE_CONTEXT_KEYWORDS)
    if not price_terms:
        return 0.0, [], "missing_price_context"

    reason_terms = _matched_terms(text, REASON_CONTEXT_KEYWORDS)
    soft_excludes = _matched_terms(text, SOFT_EXCLUDE_KEYWORDS)
    if soft_excludes and not reason_terms:
        return 0.0, soft_excludes, "market_wide_without_reason"

    score = 1.0
    if compact_name:
        score += 2.0
    score += min(len(price_terms), 3) * 1.0
    score += min(len(reason_terms), 4) * 0.8
    if soft_excludes:
        score -= min(len(soft_excludes), 3) * 0.7
    return max(score, 0.0), sorted(set(price_terms + reason_terms)), ""


def _filter_relevant_news(items: list[dict[str, Any]], stock_name: str | None = None) -> list[dict[str, Any]]:
    relevant: list[dict[str, Any]] = []
    for item in items:
        score, terms, reject_reason = _score_stock_news(item, stock_name=stock_name)
        if score <= 0:
            continue
        enriched = dict(item)
        enriched["relevance_score"] = round(score, 2)
        enriched["matched_terms"] = terms
        if reject_reason:
            enriched["reject_reason"] = reject_reason
        relevant.append(enriched)

    return sorted(
        relevant,
        key=lambda item: (
            float(item.get("relevance_score", 0.0) or 0.0),
            str(item.get("published_at", "")),
        ),
        reverse=True,
    )


def search_naver_news(query: str, display: int = 10, stock_name: str | None = None) -> list[dict[str, Any]]:
    """Search Naver News and return dashboard-safe snippets.

    No request is made unless NAVER_CLIENT_ID and NAVER_CLIENT_SECRET are set.
    Network/API failures return an empty list so the dashboard can keep rendering.
    """

    client_id, client_secret = get_naver_credentials()
    if not query or not client_id or not client_secret:
        return []

    try:
        normalized_display = min(max(1, int(display)), 100)
    except (TypeError, ValueError):
        normalized_display = 10

    try:
        response = requests.get(
            NAVER_NEWS_SEARCH_URL,
            params={"query": query, "display": normalized_display, "sort": "date"},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    built_items = [_build_news_item(item) for item in items[:normalized_display] if isinstance(item, dict)]
    return _filter_relevant_news(built_items, stock_name=stock_name)


def build_news_queries_for_mover(mover: dict[str, Any]) -> list[str]:
    name = strip_html(str(mover.get("name", "")))
    if not name:
        ticker = strip_html(str(mover.get("ticker", "")))
        name = ticker
    if not name:
        return []

    return [
        f"{name} 주가 상승 이유",
        f"{name} 급등 이유",
        f"{name} 강세 배경",
        f"{name} 실적 주가",
        f"{name} 수주 주가",
    ]
