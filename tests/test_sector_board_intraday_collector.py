from __future__ import annotations

from datetime import date

from sector_board.collector import collect_intraday_and_store


def test_collect_intraday_and_store_uses_same_day_upsert(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_BOARD_ENABLED", "true")
    captured: dict = {}

    def fake_fetch_snapshot(**_kwargs):
        return {"themes": [{"rank": 1, "theme_name": "Old"}]}

    def fake_intraday_payload(previous_snapshot=None):
        captured["previous_snapshot"] = previous_snapshot
        return {
            "generated_at": "2026-06-01T09:30:00",
            "summary": {"board_type": "intraday"},
            "themes": [],
            "leaders": [],
        }

    def fake_upsert(payload, **_kwargs):
        captured["payload"] = payload
        return {"sector_db_status": "upserted"}

    monkeypatch.setattr("sector_board.repository.fetch_snapshot", fake_fetch_snapshot)
    monkeypatch.setattr("sector_board.repository.upsert_snapshot", fake_upsert)
    monkeypatch.setattr("src.market_data.get_intraday_board_view_models", fake_intraday_payload)

    result = collect_intraday_and_store("sqlite://", snapshot_date=date(2026, 6, 1))

    assert result == {"sector_db_status": "upserted"}
    assert captured["previous_snapshot"]["themes"][0]["theme_name"] == "Old"
    assert captured["payload"]["snapshot_date"] == "2026-06-01"
    assert captured["payload"]["summary"]["snapshot_date"] == "2026-06-01"


def test_collect_intraday_and_store_disabled_preserves_morning_path(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_BOARD_ENABLED", "false")

    def fake_collect(database_url, snapshot_date=None):
        return {"database_url": database_url, "snapshot_date": snapshot_date.isoformat()}

    monkeypatch.setattr("sector_board.collector.collect_and_store", fake_collect)

    result = collect_intraday_and_store("sqlite://", snapshot_date=date(2026, 6, 1))

    assert result == {"database_url": "sqlite://", "snapshot_date": "2026-06-01"}


def test_collect_intraday_and_store_survives_evidence_failure(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_BOARD_ENABLED", "true")
    monkeypatch.setenv("INTRADAY_EVIDENCE_ENABLED", "true")
    captured: dict = {}

    def fake_fetch_snapshot(**_kwargs):
        return None

    def fake_intraday_payload(previous_snapshot=None):
        return {
            "generated_at": "2026-06-01T09:30:00",
            "summary": {"board_type": "intraday"},
            "themes": [{"theme_name": "반도체"}],
            "leaders": [{"code": "005930", "name": "삼성전자", "change_rate": 4.2, "trade_value": 10}],
        }

    def fake_upsert(payload, **_kwargs):
        captured["payload"] = payload
        return {"sector_db_status": "upserted"}

    def broken_evidence(*_args, **_kwargs):
        raise RuntimeError("evidence backend unavailable")

    monkeypatch.setattr("sector_board.repository.fetch_snapshot", fake_fetch_snapshot)
    monkeypatch.setattr("sector_board.repository.upsert_snapshot", fake_upsert)
    monkeypatch.setattr("src.market_data.get_intraday_board_view_models", fake_intraday_payload)
    monkeypatch.setattr("src.evidence_service.build_evidence_bundles_for_leaders", broken_evidence)

    result = collect_intraday_and_store("sqlite://", snapshot_date=date(2026, 6, 1))

    assert result == {"sector_db_status": "upserted"}
    assert captured["payload"]["rise_reasons"] == []
    assert captured["payload"]["summary"]["evidence_status"]["status"] == "error"
