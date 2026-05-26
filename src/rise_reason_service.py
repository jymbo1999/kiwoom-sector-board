from __future__ import annotations

import json
import os
from typing import Any

from src.config import get_openai_api_key


SUMMARY_KEYS = [
    "ticker",
    "name",
    "reason_summary_ko",
    "reason_tags",
    "evidence_titles",
    "confidence",
    "caveat",
]

ALLOWED_CONFIDENCE = {"high", "medium", "low", "unknown"}
ALLOWED_REASON_TAGS = ["실적", "정책", "수주", "섹터", "수급", "기대감"]

SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ticker": {"type": "string"},
        "name": {"type": "string"},
        "reason_summary_ko": {"type": "string"},
        "reason_tags": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_REASON_TAGS},
        },
        "evidence_titles": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "confidence": {"type": "string", "enum": sorted(ALLOWED_CONFIDENCE)},
        "caveat": {"type": "string"},
    },
    "required": SUMMARY_KEYS,
}


def _evidence_items(evidence_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    items = evidence_bundle.get("evidence", [])
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get("source_type") == "news"
    ]


def _evidence_titles(evidence_bundle: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for item in _evidence_items(evidence_bundle):
        title = str(item.get("title", "")).strip()
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= 3:
            break
    return titles


def _infer_reason_tags(evidence_bundle: dict[str, Any]) -> list[str]:
    if not _evidence_items(evidence_bundle):
        return []

    text_parts = []
    market_move = evidence_bundle.get("market_move", {})
    if isinstance(market_move, dict):
        text_parts.append(str(market_move.get("sector", "")))
    for item in _evidence_items(evidence_bundle):
        text_parts.append(str(item.get("title", "")))
        text_parts.append(str(item.get("excerpt", "")))
    text = " ".join(text_parts)

    tag_keywords = {
        "실적": ["실적", "영업이익", "매출", "잠정실적"],
        "정책": ["정책", "정부", "규제", "지원", "보조금"],
        "수주": ["수주", "공급계약", "계약"],
        "섹터": ["반도체", "2차전지", "방산", "조선", "바이오", "로봇", "AI", "원전", "섹터"],
        "수급": ["거래대금", "거래량", "기관", "외국인", "수급"],
        "기대감": ["기대", "전망", "모멘텀", "호조"],
    }
    tags = [tag for tag, keywords in tag_keywords.items() if any(keyword in text for keyword in keywords)]
    return [tag for tag in ALLOWED_REASON_TAGS if tag in tags]


def _fallback_confidence(evidence_bundle: dict[str, Any]) -> str:
    items = _evidence_items(evidence_bundle)
    if not items:
        return "unknown"

    news_count = len(items)
    market_move = evidence_bundle.get("market_move", {})
    sector = str(market_move.get("sector", "")) if isinstance(market_move, dict) else ""
    pct_change = float(market_move.get("pct_change", 0.0) or 0.0) if isinstance(market_move, dict) else 0.0

    if news_count >= 3 and sector and pct_change > 0:
        return "medium"
    if news_count > 0:
        return "low"
    return "unknown"


def _fallback_summary(evidence_bundle: dict[str, Any]) -> dict[str, Any]:
    titles = _evidence_titles(evidence_bundle)
    confidence = _fallback_confidence(evidence_bundle)
    if not titles:
        reason_summary = "관련 네이버 뉴스가 충분히 확인되지 않았습니다."
        caveat = "주가 흐름과 직접 연결된 뉴스 snippet이 부족해 요약 범위를 제한했습니다."
    else:
        title_text = ", ".join(titles[:3])
        tag_text = ", ".join(_infer_reason_tags(evidence_bundle))
        reason_summary = f"관련 뉴스에서는 {title_text} 등이 확인됩니다."
        if tag_text:
            reason_summary += f" 뉴스 snippet에는 {tag_text} 관련 표현이 함께 나타납니다."
        caveat = "제공된 네이버 뉴스 snippet을 모아 요약한 내용이며, 상승 원인을 단정하거나 투자 판단을 권유하지 않습니다."

    return {
        "ticker": str(evidence_bundle.get("ticker", "")),
        "name": str(evidence_bundle.get("name", "")),
        "reason_summary_ko": reason_summary,
        "reason_tags": _infer_reason_tags(evidence_bundle),
        "evidence_titles": titles,
        "confidence": confidence,
        "caveat": caveat,
    }


def _validate_summary(candidate: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return fallback

    normalized = {
        "ticker": str(candidate.get("ticker", fallback["ticker"])),
        "name": str(candidate.get("name", fallback["name"])),
        "reason_summary_ko": str(candidate.get("reason_summary_ko", fallback["reason_summary_ko"])),
        "reason_tags": [
            str(tag)
            for tag in candidate.get("reason_tags", fallback["reason_tags"])
            if str(tag) in ALLOWED_REASON_TAGS
        ],
        "evidence_titles": [str(title) for title in candidate.get("evidence_titles", fallback["evidence_titles"])][:3],
        "confidence": str(candidate.get("confidence", fallback["confidence"])),
        "caveat": str(candidate.get("caveat", fallback["caveat"])),
    }
    if normalized["confidence"] not in ALLOWED_CONFIDENCE:
        normalized["confidence"] = fallback["confidence"]
    return {key: normalized[key] for key in SUMMARY_KEYS}


def _system_prompt() -> str:
    return (
        "You summarize relevant Korean stock news as a strict JSON object. "
        "Use only the provided evidence. Do not infer facts that are not in evidence. "
        "Use Naver news snippets only; ignore disclosures or non-news evidence if present. "
        "Tone down causal language: summarize collected related news, not a confirmed rise reason. "
        "If evidence is weak, set confidence to low or unknown. "
        "Separate company-specific issues from sector-wide issues. "
        "Do not write investment recommendations. Do not encourage buying or selling. "
        "Return only a JSON object matching the provided schema."
    )


def _user_prompt(evidence_bundle: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "한국 주식 관련 뉴스 요약 JSON을 생성합니다.",
            "rules": [
                "제공된 evidence만 사용합니다.",
                "evidence에 없는 내용은 추측하지 않습니다.",
                "네이버 뉴스 snippet만 근거로 사용하고 공시 또는 비뉴스 근거는 사용하지 않습니다.",
                "상승 원인을 확정하지 말고, 수집된 관련 뉴스를 문단으로 요약합니다.",
                "근거가 약하면 confidence를 low 또는 unknown으로 둡니다.",
                "종목 고유 이슈와 섹터 공통 이슈를 구분합니다.",
                "투자 추천처럼 표현하지 않습니다.",
                "매수/매도 권유 문구를 쓰지 않습니다.",
                "출력은 반드시 JSON object만 반환합니다.",
            ],
            "schema": SUMMARY_JSON_SCHEMA,
            "evidence_bundle": evidence_bundle,
        },
        ensure_ascii=False,
    )


def _call_openai_summary(evidence_bundle: dict[str, Any]) -> dict[str, Any] | None:
    api_key = get_openai_api_key()
    if not api_key:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": _system_prompt()}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _user_prompt(evidence_bundle)}],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "rise_reason_summary",
                    "strict": True,
                    "schema": SUMMARY_JSON_SCHEMA,
                }
            },
        )
        output_text = getattr(response, "output_text", "")
        if not output_text:
            return None
        parsed = json.loads(output_text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def summarize_rise_reason(evidence_bundle: dict[str, Any]) -> dict[str, Any]:
    """Return a stable Korean rise-reason summary JSON for one evidence bundle."""

    fallback = _fallback_summary(evidence_bundle)
    candidate = _call_openai_summary(evidence_bundle)
    return _validate_summary(candidate, fallback)


def summarize_rise_reasons(evidence_bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return stable rise-reason summaries for many evidence bundles."""

    if not isinstance(evidence_bundles, list):
        return []
    return [
        summarize_rise_reason(bundle)
        for bundle in evidence_bundles
        if isinstance(bundle, dict)
    ]
