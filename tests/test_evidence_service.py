from __future__ import annotations

from src.evidence_service import (
    build_evidence_bundle,
    build_evidence_bundles,
    build_evidence_bundles_for_leaders,
)


MOCK_MOVER = {
    "ticker": "005930",
    "name": "삼성전자",
    "market": "KOSPI",
    "sector": "반도체",
    "pct_change": 3.2,
    "volume_rank": 1,
    "trading_value": 123_456_789_000,
}


def test_build_evidence_bundle_returns_required_structure_without_api_keys(monkeypatch) -> None:
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    bundle = build_evidence_bundle(MOCK_MOVER, trade_date="2026-05-26")

    assert isinstance(bundle, dict)
    assert list(bundle.keys()) == [
        "trade_date",
        "ticker",
        "name",
        "market",
        "market_move",
        "evidence",
    ]
    assert bundle["trade_date"] == "2026-05-26"
    assert bundle["ticker"] == "005930"
    assert bundle["name"] == "삼성전자"
    assert bundle["market"] == "KOSPI"
    assert bundle["market_move"] == {
        "pct_change": 3.2,
        "volume_rank": 1,
        "sector": "반도체",
        "trading_value": 123_456_789_000,
    }
    assert bundle["evidence"] == []


def test_build_evidence_bundles_returns_limited_list_without_api_keys(monkeypatch) -> None:
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    bundles = build_evidence_bundles(date="2026-05-26", limit=3)

    assert isinstance(bundles, list)
    assert len(bundles) <= 3
    assert bundles
    assert all("evidence" in bundle for bundle in bundles)


def test_build_evidence_bundle_uses_naver_news_only(monkeypatch) -> None:
    def fake_queries(_mover):
        return ["삼성전자 상승"]

    def fake_news(*_args, **_kwargs):
        return [
            {
                "source_type": "news",
                "provider": "Naver",
                "title": "삼성전자 상승",
                "published_at": "2026-05-26T10:00:00",
                "url": "https://news.example/a",
                "excerpt": "뉴스 요약",
                "weight": 0.5,
                "relevance_score": 5.8,
                "matched_terms": ["상승", "주가"],
            },
            {
                "source_type": "news",
                "provider": "Naver",
                "title": "삼성전자 상승",
                "published_at": "2026-05-26T10:01:00",
                "url": "https://news.example/b",
                "excerpt": "중복 제목",
                "weight": 0.5,
            },
        ]

    monkeypatch.setattr("src.evidence_service.build_news_queries_for_mover", fake_queries)
    monkeypatch.setattr("src.evidence_service.search_naver_news", fake_news)

    evidence = build_evidence_bundle(MOCK_MOVER)["evidence"]

    assert [item["source_type"] for item in evidence] == ["news"]
    assert len(evidence) == 1
    assert evidence[0]["relevance_score"] == 5.8
    assert evidence[0]["matched_terms"] == ["상승", "주가"]


def test_build_evidence_bundles_for_leaders_maps_intraday_leaders(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_bundle(mover, trade_date=None):
        captured.append({"mover": mover, "trade_date": trade_date})
        return {"ticker": mover["ticker"], "name": mover["name"], "market_move": mover, "evidence": []}

    monkeypatch.setattr("src.evidence_service.build_evidence_bundle", fake_bundle)

    bundles = build_evidence_bundles_for_leaders(
        [
            {
                "code": "005930",
                "name": "삼성전자",
                "theme_name": "반도체",
                "change_rate": 4.2,
                "rank": 1,
                "trade_value": 123_000_000_000,
            },
            {
                "code": "000660",
                "name": "SK하이닉스",
                "theme_id": "반도체",
                "change_rate": 3.1,
                "rank": 2,
                "trade_value": 100_000_000_000,
            },
        ],
        limit=1,
        trade_date="2026-06-01",
    )

    assert len(bundles) == 1
    assert captured[0]["trade_date"] == "2026-06-01"
    assert captured[0]["mover"]["ticker"] == "005930"
    assert captured[0]["mover"]["sector"] == "반도체"
    assert captured[0]["mover"]["pct_change"] == 4.2


def test_build_evidence_bundles_for_leaders_fails_open(monkeypatch) -> None:
    def broken_bundle(*_args, **_kwargs):
        raise RuntimeError("news unavailable")

    monkeypatch.setattr("src.evidence_service.build_evidence_bundle", broken_bundle)

    bundles = build_evidence_bundles_for_leaders(
        [{"code": "005930", "name": "삼성전자", "change_rate": 4.2}],
        limit=10,
    )

    assert bundles == []
