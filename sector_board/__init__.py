from __future__ import annotations

from typing import Any
import os

from flask import Flask

from .blueprint import create_sector_board_blueprint
from .repository import ensure_schema, resolve_database_url


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


__all__ = ["create_app", "register_sector_board"]
