from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask

from .blueprint import create_sector_board_blueprint
from .repository import ensure_schema, resolve_database_url

_log = logging.getLogger(__name__)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.update(
        SECRET_KEY="sector-board-dev",
        SECTOR_BOARD_LAYOUT_TEMPLATE="sector_board/standalone.html",
        SECTOR_BOARD_NO_AUTH=True,
    )
    if config:
        app.config.update(config)
    register_sector_board(app, url_prefix="/sector-board")

    @app.route("/")
    def root():
        from flask import redirect, url_for

        return redirect(url_for("sector_board.index"))

    return app


def register_sector_board(app: Flask, url_prefix: str = "/sector-board") -> None:
    app.register_blueprint(create_sector_board_blueprint(), url_prefix=url_prefix)
    database_url = resolve_database_url(app=app)
    auto_create = app.config.get("SECTOR_BOARD_AUTO_CREATE_TABLE") or (
        os.getenv("SECTOR_BOARD_AUTO_CREATE_TABLE", "").strip().lower() in {"1", "true", "yes", "on"}
    )
    if database_url and auto_create:
        ensure_schema(database_url=database_url)

    if database_url:
        _setup_scheduler(database_url)


def _setup_scheduler(database_url: str) -> None:
    """KRX 모드일 때 일일 스케줄러 등록 및 시작 시 수집 여부 확인."""
    try:
        from src.config import load_settings
        settings = load_settings()
        if not settings.use_krx_data:
            return

        from .scheduler import setup_daily_scheduler, trigger_startup_collect_if_needed
        setup_daily_scheduler(database_url, collect_hour=settings.krx_collect_hour)
        trigger_startup_collect_if_needed(database_url)
    except Exception as exc:
        _log.warning("[sector-board] 스케줄러 설정 실패 (무시): %s", exc)


__all__ = ["create_app", "register_sector_board"]
