from __future__ import annotations

from email.utils import parsedate_to_datetime
from html import unescape
import os
import re
from typing import Any

import requests


NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
NEWS_WEIGHT = 0.5


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


def search_naver_news(query: str, display: int = 10) -> list[dict[str, Any]]:
    """Search Naver News and return dashboard-safe snippets.

    No request is made unless NAVER_CLIENT_ID and NAVER_CLIENT_SECRET are set.
    Network/API failures return an empty list so the dashboard can keep rendering.
    """

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
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
    return [_build_news_item(item) for item in items[:normalized_display] if isinstance(item, dict)]


def build_news_queries_for_mover(mover: dict[str, Any]) -> list[str]:
    name = strip_html(str(mover.get("name", "")))
    if not name:
        ticker = strip_html(str(mover.get("ticker", "")))
        name = ticker
    if not name:
        return []

    return [
        f"{name} 주가",
        f"{name} 상승",
        f"{name} 수주",
        f"{name} 실적",
        f"{name} 정책",
    ]
