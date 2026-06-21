# tests/test_intraday_news_repository.py
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(eng)
    return eng


def _cand():
    return {
        "event_type": "rise", "scope": "stock", "sector_name": "로봇",
        "stock_code": "277810", "stock_name": "레인보우로보틱스",
        "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x",
    }


def test_upsert_event_creates_then_cooldown_updates(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    id1 = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    # 5분 뒤 같은 종목+타입 → 신규 없음(쿨다운), 같은 id 갱신
    id2 = nr.upsert_event(eng, {**_cand(), "change_rate": 0.15}, trade_date=date(2026, 6, 21), now=t0 + timedelta(minutes=5))
    assert id1 == id2
    assert len(nr.list_events_for_date(eng, date(2026, 6, 21))) == 1


def test_upsert_event_new_after_cooldown(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0 + timedelta(minutes=31))
    assert len(nr.list_events_for_date(eng, date(2026, 6, 21))) == 2


def test_insert_article_dedupes(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    a = {"title": "로봇주 급등", "url": "http://x/1", "source": "Naver",
         "published_at": "2026-06-21", "description": "", "query": "q", "stage": "T0",
         "dedupe_key": "url:http://x/1"}
    assert nr.insert_article(eng, ev, a, now=t0) is True
    assert nr.insert_article(eng, ev, a, now=t0) is False  # 중복
    assert len(nr.list_articles_for_event(eng, ev)) == 1


def test_unread_and_mark_read(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    assert nr.count_unread(eng, date(2026, 6, 21)) == 1
    nr.mark_read(eng, date(2026, 6, 21), now=t0)
    assert nr.count_unread(eng, date(2026, 6, 21)) == 0


def test_storage_stats(tmp_path):
    eng = _engine(tmp_path)
    t0 = datetime(2026, 6, 21, 9, 18)
    ev = nr.upsert_event(eng, _cand(), trade_date=date(2026, 6, 21), now=t0)
    nr.insert_article(eng, ev, {"title": "t", "url": "http://x/1", "dedupe_key": "url:http://x/1", "stage": "T0"}, now=t0)
    stats = nr.get_storage_stats(eng)
    assert stats["total_events"] == 1
    assert stats["total_articles"] == 1
    assert stats["total_bytes"] > 0
    assert isinstance(stats["total_human"], str)
