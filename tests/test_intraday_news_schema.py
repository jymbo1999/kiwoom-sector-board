from sqlalchemy import create_engine, inspect
from sector_board.news_schema import ensure_news_schema


def test_ensure_news_schema_creates_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'news.db'}", future=True)
    ensure_news_schema(engine)
    names = set(inspect(engine).get_table_names())
    assert {"intraday_news_events", "intraday_news_articles"} <= names

    cols = {c["name"] for c in inspect(engine).get_columns("intraday_news_events")}
    assert {"trade_date", "event_type", "scope", "status", "is_read", "payload_json"} <= cols
    acols = {c["name"] for c in inspect(engine).get_columns("intraday_news_articles")}
    assert {"event_id", "url", "dedupe_key", "stage"} <= acols
