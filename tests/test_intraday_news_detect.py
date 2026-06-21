# tests/test_intraday_news_detect.py
from sector_board.intraday_news import normalize_title, article_dedupe_key


def test_normalize_title_strips_and_lowers():
    assert normalize_title("<b>로봇주</b> 급등! (특징주)") == "로봇주급등특징주"


def test_dedupe_key_prefers_url():
    item = {"title": "A", "url": "http://x/1", "published_at": "2026-06-21", "provider": "Naver"}
    assert article_dedupe_key(item) == "url:http://x/1"


def test_dedupe_key_falls_back_to_title_hash():
    item = {"title": "로봇주 급등", "url": "", "published_at": "2026-06-21", "provider": "Naver"}
    key = article_dedupe_key(item)
    assert key.startswith("h:") and len(key) > 10
