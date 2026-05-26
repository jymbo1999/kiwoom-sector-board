from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests

from src.config import get_opendart_api_key


DART_DISCLOSURE_SEARCH_URL = "https://opendart.fss.or.kr/api/list.json"
DART_WEIGHT = 1.0

IMPORTANT_DART_KEYWORDS = [
    "공급계약",
    "단일판매",
    "수주",
    "영업실적",
    "잠정실적",
    "무상증자",
    "유상증자",
    "자기주식",
    "합병",
    "투자",
    "최대주주",
]


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _normalize_report_date(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) != 8:
        return str(value)
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}T00:00:00"


def _build_disclosure_item(item: dict[str, Any]) -> dict[str, Any]:
    rcept_no = str(item.get("rcept_no", ""))
    url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else ""
    title = str(item.get("report_nm", ""))
    corp_name = str(item.get("corp_name", ""))

    return {
        "source_type": "dart",
        "provider": "OpenDART",
        "title": title,
        "published_at": _normalize_report_date(item.get("rcept_dt")),
        "url": url,
        "excerpt": f"{corp_name} {title}".strip(),
        "weight": DART_WEIGHT,
    }


def search_dart_disclosures(ticker: str, corp_name: str, days: int = 7) -> list[dict[str, Any]]:
    """Search OpenDART disclosures and return dashboard-safe evidence items.

    No request is made unless OPENDART_API_KEY is set. OpenDART usually needs
    corp_code for precise lookup; this shell keeps ticker/corp_name inputs stable
    for the dashboard and searches by company name until corp-code mapping exists.
    """

    api_key = get_opendart_api_key()
    if not api_key:
        return []

    query_name = str(corp_name or "").strip()
    if not query_name:
        return []

    try:
        normalized_days = max(1, int(days))
    except (TypeError, ValueError):
        normalized_days = 7

    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=normalized_days)
        response = requests.get(
            DART_DISCLOSURE_SEARCH_URL,
            params={
                "crtfc_key": api_key,
                "bgn_de": _format_date(start_date),
                "end_de": _format_date(end_date),
                "corp_name": query_name,
                "page_count": 20,
            },
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, OverflowError):
        return []

    if str(payload.get("status", "")) not in {"000", "013"}:
        return []

    items = payload.get("list", [])
    if not isinstance(items, list):
        return []

    ticker_text = str(ticker or "").strip()
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if ticker_text and str(item.get("stock_code", "")).strip() not in {"", ticker_text}:
            continue
        results.append(_build_disclosure_item(item))
    return results
