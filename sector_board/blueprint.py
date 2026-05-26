from __future__ import annotations

from datetime import date
from math import isfinite

from flask import Blueprint, current_app, jsonify, render_template
from sqlalchemy.exc import SQLAlchemyError

from .auth import auth_gate
from .repository import fetch_snapshot, resolve_database_url


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _format_pct(value: object) -> str:
    return f"{_to_float(value):+.2f}%"


def _format_krw(value: object) -> str:
    number = _to_float(value)
    if number >= 1_0000_0000_0000:
        return f"{number / 1_0000_0000_0000:.1f}조원"
    if number >= 1_0000_0000:
        return f"{number / 1_0000_0000:.0f}억원"
    return f"{number:,.0f}원"


def _build_sector_rows(themes: list[dict], leaders: list[dict], limit: int = 12) -> list[dict]:
    leaders_by_theme: dict[str, list[dict]] = {}
    for leader in leaders:
        theme_id = str(leader.get("theme_id") or leader.get("sector") or "")
        if not theme_id:
            continue
        leaders_by_theme.setdefault(theme_id, []).append(leader)

    sorted_themes = sorted(
        themes,
        key=lambda row: (_to_float(row.get("theme_score")), _to_float(row.get("total_trading_value"))),
        reverse=True,
    )[:limit]

    rows = []
    for rank, theme in enumerate(sorted_themes, start=1):
        theme_id = str(theme.get("theme_id") or theme.get("sector") or theme.get("theme_name") or "")
        theme_leaders = sorted(
            leaders_by_theme.get(theme_id, []),
            key=lambda item: int(_to_float(item.get("rank"), 999)),
        )[:5]
        rows.append(
            {
                "rank": rank,
                "theme_id": theme_id,
                "theme_name": str(theme.get("theme_name") or theme.get("sector") or theme_id),
                "theme_score": _to_float(theme.get("theme_score")),
                "top5_change_rate_mean": _format_pct(theme.get("top5_change_rate_mean")),
                "total_trading_value": _format_krw(theme.get("total_trading_value")),
                "leader_labels": str(theme.get("leader_labels") or ""),
                "leaders": [
                    {
                        "rank": int(_to_float(leader.get("rank"), idx)),
                        "name": str(leader.get("name") or ""),
                        "code": str(leader.get("code") or ""),
                        "change_rate": _format_pct(leader.get("change_rate")),
                        "trade_value": _format_krw(leader.get("trade_value")),
                    }
                    for idx, leader in enumerate(theme_leaders, start=1)
                ],
            }
        )
    return rows


def create_sector_board_blueprint() -> Blueprint:
    blueprint = Blueprint(
        "sector_board",
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    @blueprint.before_request
    def require_auth():
        return auth_gate()

    @blueprint.route("/", strict_slashes=False)
    def index():
        database_url = resolve_database_url(app=current_app)
        snapshot = None
        error_message = None
        if database_url:
            try:
                snapshot = fetch_snapshot(database_url=database_url, snapshot_date=date.today())
            except SQLAlchemyError as exc:
                error_message = str(exc)
        else:
            error_message = "SECTOR_BOARD_DATABASE_URL is not configured."

        return render_template(
            "sector_board/index.html",
            layout_template=current_app.config.get("SECTOR_BOARD_LAYOUT_TEMPLATE", "sector_board/standalone.html"),
            snapshot=snapshot,
            summary=(snapshot or {}).get("summary", {}),
            sector_rows=_build_sector_rows(
                (snapshot or {}).get("themes", []),
                (snapshot or {}).get("leaders", []),
            ),
            error_message=error_message,
        )

    @blueprint.route("/api/snapshot")
    def api_snapshot():
        database_url = resolve_database_url(app=current_app)
        if not database_url:
            return jsonify({"ok": False, "error": "SECTOR_BOARD_DATABASE_URL is not configured."}), 503
        snapshot = fetch_snapshot(database_url=database_url)
        if snapshot is None:
            return jsonify({"ok": False, "snapshot": None}), 404
        return jsonify({"ok": True, "snapshot": snapshot})

    @blueprint.route("/health")
    def health():
        database_url = resolve_database_url(app=current_app)
        if not database_url:
            return jsonify({"ok": False, "database": "missing"}), 503
        try:
            snapshot = fetch_snapshot(database_url=database_url)
        except SQLAlchemyError as exc:
            return jsonify({"ok": False, "database": "error", "error": str(exc)}), 503
        return jsonify(
            {
                "ok": True,
                "database": "ok",
                "latest_snapshot_date": None if snapshot is None else snapshot.get("snapshot_date"),
                "latest_generated_at": None if snapshot is None else snapshot.get("generated_at"),
            }
        )

    return blueprint
