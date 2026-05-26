from __future__ import annotations

import requests

from src.dart_service import IMPORTANT_DART_KEYWORDS, search_dart_disclosures


def test_search_dart_disclosures_without_api_key_returns_empty_list(monkeypatch) -> None:
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)

    results = search_dart_disclosures("005930", "삼성전자")

    assert isinstance(results, list)
    assert results == []


def test_search_dart_disclosures_without_api_key_does_not_call_network(monkeypatch) -> None:
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)

    def fail_get(*_args, **_kwargs):
        raise AssertionError("network should not be called without OPENDART_API_KEY")

    monkeypatch.setattr(requests, "get", fail_get)

    assert search_dart_disclosures("005930", "삼성전자") == []


def test_important_dart_keywords_include_contract_terms() -> None:
    assert "공급계약" in IMPORTANT_DART_KEYWORDS
    assert "단일판매" in IMPORTANT_DART_KEYWORDS
