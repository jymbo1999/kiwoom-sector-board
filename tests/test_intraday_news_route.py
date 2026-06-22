from datetime import date, datetime

from flask import Flask
from sqlalchemy import create_engine
from sector_board import register_sector_board, register_intraday
from sector_board.news_schema import ensure_news_schema
from sector_board import news_repository as nr


def _app(tmp_path, monkeypatch):
    monkeypatch.delenv("SECTOR_BOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = Flask(__name__)
    db_url = f"sqlite:///{tmp_path/'news.db'}"
    app.config["SECTOR_BOARD_DATABASE_URL"] = db_url
    app.config["SECTOR_BOARD_LAYOUT_TEMPLATE"] = "sector_board/standalone.html"
    register_sector_board(app)
    register_intraday(app)
    eng = create_engine(db_url, future=True)
    ensure_news_schema(eng)
    nr.upsert_event(eng, {"event_type": "rise", "scope": "stock", "sector_name": "로봇",
                          "stock_code": "277810", "stock_name": "레인보우로보틱스",
                          "change_rate": 0.12, "short_change_rate": None, "trigger_reason": "x"},
                    trade_date=date.today(), now=datetime.now())
    return app


def test_news_tab_renders(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    c = app.test_client()
    assert c.get("/intraday").status_code == 200            # 기본 price
    r = c.get("/intraday?tab=news")
    assert r.status_code == 200
    assert "레인보우로보틱스" in r.get_data(as_text=True)
    r2 = c.get("/intraday?tab=daily-log")
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert "총 이벤트" in body and "전체 용량" in body
