# tests/test_intraday_news_collect.py
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr
from sector_board.intraday_news import collect_news_for_event


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(eng)
    return eng


def _fake_search(query, display=10, stock_name=None):
    return [{"title": "로봇주 급등", "url": "http://x/1", "provider": "Naver",
             "published_at": "2026-06-21", "excerpt": "내용"}]


def test_collect_stores_then_dedupes_across_stages(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": "로봇",
                               "stock_code": "277810", "stock_name": "레인보우로보틱스",
                               "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                         trade_date=date(2026, 6, 21), now=t0)
    event = nr.list_events_for_date(eng, date(2026, 6, 21))[0]
    added0 = collect_news_for_event(eng, event, "T0", now=t0, search_fn=_fake_search)
    added10 = collect_news_for_event(eng, event, "T+10", now=t0 + timedelta(minutes=10), search_fn=_fake_search)
    assert added0 == 1
    assert added10 == 0  # 같은 기사 → dedupe
    assert len(nr.list_articles_for_event(eng, ev)) == 1


def test_collect_handles_search_failure(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": None,
                               "stock_code": "277810", "stock_name": "레인보우로보틱스",
                               "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                         trade_date=date(2026, 6, 21), now=t0)
    event = nr.list_events_for_date(eng, date(2026, 6, 21))[0]

    def boom(*a, **k):
        raise RuntimeError("naver down")

    assert collect_news_for_event(eng, event, "T0", now=t0, search_fn=boom) == 0  # 예외 삼킴
