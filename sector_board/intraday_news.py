# sector_board/intraday_news.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

RISE_PCT = 0.08
FALL_PCT = -0.08
SECTOR_STOCK_PCT = 0.10
SECTOR_MIN_STOCKS = 3
STAGE_OFFSETS = {"T0": 0, "T+10": 10, "T+30": 30}

_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")
_TAG = re.compile(r"<[^>]+>")


def normalize_title(title: str | None) -> str:
    text = _TAG.sub("", str(title or ""))
    text = text.lower()
    text = _NON_WORD.sub("", text)
    return text


def article_dedupe_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        return f"url:{url}"
    basis = normalize_title(item.get("title")) + "|" + str(item.get("provider") or "") + "|" + str(item.get("published_at") or "")
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
    return f"h:{digest}"
