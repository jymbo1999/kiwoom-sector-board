from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from math import isfinite

from flask import Blueprint, current_app, jsonify, redirect, render_template, url_for
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


def _compute_rank_changes(today_themes: list[dict], yesterday_themes: list[dict], limit: int = 12) -> dict[str, str]:
    if not today_themes:
        return {}
    sorted_today = sorted(
        today_themes,
        key=lambda t: (_to_float(t.get("theme_score")), _to_float(t.get("total_trading_value"))),
        reverse=True,
    )[:limit]
    today_ranks = {str(t.get("theme_name", "")): i + 1 for i, t in enumerate(sorted_today)}
    if not yesterday_themes:
        return {name: "NEW" for name in today_ranks}
    sorted_yesterday = sorted(
        yesterday_themes,
        key=lambda t: (_to_float(t.get("theme_score")), _to_float(t.get("total_trading_value"))),
        reverse=True,
    )[:limit]
    yesterday_ranks = {str(t.get("theme_name", "")): i + 1 for i, t in enumerate(sorted_yesterday)}
    result: dict[str, str] = {}
    for name, today_rank in today_ranks.items():
        if name not in yesterday_ranks:
            result[name] = "NEW"
        else:
            diff = yesterday_ranks[name] - today_rank
            if diff > 0:
                result[name] = f"▲{diff}"
            elif diff < 0:
                result[name] = f"▼{abs(diff)}"
            else:
                result[name] = "="
    return result


def _build_sector_rows(themes: list[dict], leaders: list[dict], rank_changes: dict[str, str] | None = None, limit: int = 12) -> list[dict]:
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
        theme_name = str(theme.get("theme_name") or theme.get("sector") or theme_id)
        theme_leaders = sorted(
            leaders_by_theme.get(theme_id, []),
            key=lambda item: int(_to_float(item.get("rank"), 999)),
        )[:5]
        badges_raw = str(theme.get("badges") or "")
        rows.append(
            {
                "rank": rank,
                "theme_id": theme_id,
                "theme_name": theme_name,
                "theme_score": _to_float(theme.get("theme_score")),
                "top5_change_rate_mean": _format_pct(theme.get("top5_change_rate_mean")),
                "top5_change_rate_mean_val": _to_float(theme.get("top5_change_rate_mean")),
                "total_trading_value": _format_krw(theme.get("total_trading_value")),
                "leader_labels": str(theme.get("leader_labels") or ""),
                "rising_ratio": _to_float(theme.get("rising_ratio")),
                "badges": [b.strip() for b in badges_raw.split(",") if b.strip()],
                "rank_change": (rank_changes or {}).get(theme_name, "NEW"),
                "leaders": [
                    {
                        "rank": int(_to_float(leader.get("rank"), idx)),
                        "name": str(leader.get("name") or ""),
                        "code": str(leader.get("code") or ""),
                        "change_rate": _format_pct(leader.get("change_rate")),
                        "change_rate_val": _to_float(leader.get("change_rate")),
                        "trade_value": _format_krw(leader.get("trade_value")),
                    }
                    for idx, leader in enumerate(theme_leaders, start=1)
                ],
            }
        )
    return rows


def _get_max_age_seconds() -> int:
    try:
        return max(60, int(os.environ.get("SECTOR_BOARD_REFRESH_MAX_AGE_SECONDS") or 900))
    except (TypeError, ValueError):
        return 900


def _is_snapshot_stale(snapshot: dict) -> bool:
    """Return True if the snapshot is older than SECTOR_BOARD_REFRESH_MAX_AGE_SECONDS."""
    generated_at_str = snapshot.get("generated_at")
    if not generated_at_str:
        return False
    try:
        generated_at = datetime.fromisoformat(generated_at_str)
        return (datetime.now() - generated_at).total_seconds() > _get_max_age_seconds()
    except (ValueError, TypeError):
        return False


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
        refresh_status = "idle"
        refresh_error_msg = None

        if not database_url:
            error_message = "SECTOR_BOARD_DATABASE_URL이 설정되지 않았습니다."
        else:
            try:
                snapshot = fetch_snapshot(database_url=database_url, snapshot_date=date.today())
            except SQLAlchemyError as exc:
                error_message = str(exc)

            if snapshot is not None:
                refresh_status = snapshot.get("refresh_status") or "success"
                refresh_error_msg = snapshot.get("refresh_error")

            # Decide whether to trigger auto-collect
            needs_collect = (
                snapshot is None
                or (refresh_status == "error" and not snapshot.get("themes"))
            )
            if needs_collect and not error_message:
                try:
                    from .collector import schedule_background_collect
                    schedule_background_collect(database_url)
                    refresh_status = "running"
                except ImportError:
                    error_message = "수집 모듈(src)을 불러올 수 없습니다. 패키지 설정을 확인하세요."
                except Exception as exc:
                    error_message = f"데이터 수집 시작 실패: {exc}"

        has_data = (
            snapshot is not None
            and refresh_status not in ("running",)
            and bool((snapshot or {}).get("themes"))
        )

        today_themes = (snapshot or {}).get("themes", []) if has_data else []
        yesterday_snapshot = None
        if database_url and has_data:
            try:
                yesterday_snapshot = fetch_snapshot(
                    database_url=database_url,
                    snapshot_date=date.today() - timedelta(days=1),
                )
            except Exception:
                pass
        rank_changes = _compute_rank_changes(
            today_themes,
            (yesterday_snapshot or {}).get("themes", []),
        )
        treemap_json = json.dumps(today_themes, ensure_ascii=False)

        return render_template(
            "sector_board/index.html",
            layout_template=current_app.config.get(
                "SECTOR_BOARD_LAYOUT_TEMPLATE", "sector_board/standalone.html"
            ),
            snapshot=snapshot if has_data else None,
            summary=(snapshot or {}).get("summary", {}) if has_data else {},
            sector_rows=_build_sector_rows(
                today_themes,
                (snapshot or {}).get("leaders", []),
                rank_changes=rank_changes,
            ) if has_data else [],
            treemap_json=treemap_json,
            error_message=error_message,
            refresh_status=refresh_status,
            refresh_error=refresh_error_msg,
        )

    @blueprint.route("/refresh", methods=["POST"])
    def refresh():
        database_url = resolve_database_url(app=current_app)
        if database_url:
            try:
                from .collector import schedule_background_collect
                schedule_background_collect(database_url)
            except Exception:
                pass
        return redirect(url_for("sector_board.index"))

    @blueprint.route("/api/snapshot")
    def api_snapshot():
        database_url = resolve_database_url(app=current_app)
        if not database_url:
            return jsonify({"ok": False, "error": "SECTOR_BOARD_DATABASE_URL is not configured."}), 503
        snapshot = fetch_snapshot(database_url=database_url)
        if snapshot is None:
            return jsonify({"ok": False, "snapshot": None}), 404
        return jsonify({"ok": True, "snapshot": snapshot})

    @blueprint.route("/debug")
    def debug():
        import sys, os, platform, traceback as tb
        info: dict = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "sys_path": sys.path[:8],
        }

        # --- src.market_data import test ---
        try:
            import src.market_data as md
            info["src_market_data_file"] = getattr(md, "__file__", "?")
            info["src_market_data_has_gmb"] = hasattr(md, "get_morning_board_view_models")
            info["src_market_data_functions"] = [
                k for k in dir(md) if not k.startswith("__")
            ]
        except Exception as exc:
            info["src_market_data_error"] = tb.format_exc()

        # --- src.config / DATA_DIR ---
        try:
            from src.config import DATA_DIR, load_settings
            info["DATA_DIR"] = str(DATA_DIR)
            info["DATA_DIR_exists"] = DATA_DIR.exists()
            info["DATA_DIR_files"] = [f.name for f in DATA_DIR.iterdir()] if DATA_DIR.exists() else []
            s = load_settings()
            info["kiwoom_use_mock"] = s.use_mock
            info["theme_map_path"] = str(s.theme_map_path)
            info["theme_map_exists"] = s.theme_map_path.exists()
            info["sample_prices_path"] = str(s.sample_prices_path)
            info["sample_prices_exists"] = s.sample_prices_path.exists()
        except Exception as exc:
            info["src_config_error"] = tb.format_exc()

        # --- sector_board DB ---
        database_url = resolve_database_url(app=current_app)
        info["database_url_set"] = bool(database_url)
        if database_url:
            try:
                from .repository import fetch_snapshot
                snap = fetch_snapshot(database_url=database_url)
                info["latest_snapshot_date"] = snap.get("snapshot_date") if snap else None
                info["latest_refresh_status"] = snap.get("refresh_status") if snap else None
            except Exception as exc:
                info["db_error"] = str(exc)

        # --- env vars (masked) ---
        info["env"] = {
            "KIWOOM_USE_MOCK": os.getenv("KIWOOM_USE_MOCK"),
            "KIWOOM_APP_KEY": "***" if os.getenv("KIWOOM_APP_KEY") else None,
            "SECTOR_BOARD_AUTO_CREATE_TABLE": os.getenv("SECTOR_BOARD_AUTO_CREATE_TABLE"),
            "SECTOR_BOARD_DATABASE_URL": "***" if os.getenv("SECTOR_BOARD_DATABASE_URL") else None,
            "MORNING_BOARD_MAX_CODES": os.getenv("MORNING_BOARD_MAX_CODES"),
        }

        return jsonify(info)

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
                "refresh_status": None if snapshot is None else snapshot.get("refresh_status"),
            }
        )

    return blueprint
