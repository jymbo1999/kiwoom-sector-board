from __future__ import annotations

from flask import current_app, redirect, request, url_for


def auth_gate():
    if current_app.config.get("SECTOR_BOARD_NO_AUTH"):
        return None

    try:
        from flask_login import current_user
    except ModuleNotFoundError:
        return None

    if getattr(current_user, "is_authenticated", False):
        return None

    try:
        login_url = url_for("authentication_blueprint.login", next=request.url)
    except Exception:
        login_url = "/login"
    return redirect(login_url)
