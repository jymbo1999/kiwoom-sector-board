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
        "삼성전자 주가 상승 이유",
        "삼성전자 급등 이유",
        "삼성전자 강세 배경",
        "삼성전자 실적 주가",
        "삼성전자 수주 주가",
    ]


def test_search_naver_news_filters_to_stock_price_related_items(monkeypatch) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver-secret")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "items": [
                    {
                        "title": "<b>삼성전자</b>, HBM 기대감에 주가 강세",
                        "description": "삼성전자 주가가 HBM 실적 기대감으로 상승했다는 분석이 나왔다.",
                        "originallink": "https://news.example/good",
                        "pubDate": "Tue, 26 May 2026 10:00:00 +0900",
                    },
                    {
                        "title": "코스피, 장중 최고치 경신",
                        "description": "삼성전자 등 대형주 전반이 오름세를 보였다.",
                        "originallink": "https://news.example/market",
                        "pubDate": "Tue, 26 May 2026 10:01:00 +0900",
                    },
                    {
                        "title": "삼성전자 임직원 봉사활동 확대",
                        "description": "지역사회 공헌 프로그램을 확대했다.",
                        "originallink": "https://news.example/soft",
                        "pubDate": "Tue, 26 May 2026 10:02:00 +0900",
                    },
                    {
                        "title": "삼성전자 레버리지 ETF 거래 증가",
                        "description": "ETF 투자자 관심이 커졌다.",
                        "originallink": "https://news.example/etf",
                        "pubDate": "Tue, 26 May 2026 10:03:00 +0900",
                    },
                    {
                        "title": "삼성전자 올인한 투자자 계좌 인증",
                        "description": "삼성전자 주가 상승으로 수익률이 커졌다는 인증 글이 화제다.",
                        "originallink": "https://news.example/account",
                        "pubDate": "Tue, 26 May 2026 10:04:00 +0900",
                    },
                    {
                        "title": "경쟁사는 웃고 삼성전자는 울고",
                        "description": "삼성전자 주가가 하락하며 약세를 보였다.",
                        "originallink": "https://news.example/down",
                        "pubDate": "Tue, 26 May 2026 10:05:00 +0900",
                    },
                ]
            }

    def fake_get(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("src.news_service.requests.get", fake_get)

    results = search_naver_news("삼성전자 주가 상승 이유", display=10, stock_name="삼성전자")

    assert len(results) == 1
    assert results[0]["title"] == "삼성전자, HBM 기대감에 주가 강세"
    assert results[0]["relevance_score"] > 0
    assert "주가" in results[0]["matched_terms"]
