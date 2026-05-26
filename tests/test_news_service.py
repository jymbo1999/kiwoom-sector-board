from __future__ import annotations

from src.news_service import build_news_queries_for_mover, search_naver_news, strip_html


def test_search_naver_news_without_api_key_returns_empty_list(monkeypatch) -> None:
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    results = search_naver_news("삼성전자 상승", display=5)

    assert isinstance(results, list)
    assert results == []


def test_search_naver_news_display_argument_is_safe_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    results = search_naver_news("삼성전자 상승", display=1)

    assert isinstance(results, list)
    assert len(results) <= 1


def test_strip_html_removes_tags_and_decodes_entities() -> None:
    assert strip_html("<b>삼성전자</b> HBM&nbsp;기대감") == "삼성전자 HBM\u00a0기대감"


def test_build_news_queries_for_mover_uses_mover_name() -> None:
    queries = build_news_queries_for_mover({"ticker": "005930", "name": "삼성전자"})

    assert queries == [
        "삼성전자 주가",
        "삼성전자 상승",
        "삼성전자 수주",
        "삼성전자 실적",
        "삼성전자 정책",
    ]
