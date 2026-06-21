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


from sector_board.intraday_news import extract_movers_from_snapshot, detect_intraday_news_events


def _snap():
    return {
        "leaders": [
            {"base_code": "277810", "name": "레인보우로보틱스", "sector_name": "로봇", "last_change_rate": 0.12},
            {"base_code": "454910", "name": "두산로보틱스", "sector_name": "로봇", "last_change_rate": 0.11},
            {"base_code": "058610", "name": "에스피지", "sector_name": "로봇", "last_change_rate": 0.10},
            {"base_code": "000001", "name": "잔잔주", "sector_name": "기타", "last_change_rate": 0.01},
        ],
        "sectors": [{"sector_name": "로봇", "average_change_rate": 0.11}],
    }


def test_extract_movers_tolerant_keys():
    movers = extract_movers_from_snapshot(_snap())
    assert movers["leaders"][0]["stock_code"] == "277810"
    assert movers["leaders"][0]["change_rate"] == 0.12


def test_detect_stock_rise_event():
    cands = detect_intraday_news_events(_snap(), top5_sectors=[])
    rises = [c for c in cands if c["scope"] == "stock" and c["event_type"] == "rise"]
    assert any(c["stock_code"] == "277810" for c in rises)
    assert all(c["stock_code"] != "000001" for c in rises)  # +1% 는 임계 미달


def test_detect_sector_event_three_strong_stocks():
    cands = detect_intraday_news_events(_snap(), top5_sectors=[])
    sector = [c for c in cands if c["scope"] == "sector"]
    assert any(c["sector_name"] == "로봇" for c in sector)
