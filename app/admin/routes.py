from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, abort
from flask_login import login_required, current_user

from app.config_loader import read_raw_text, write_raw_text

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _config_registry():
    cfg = current_app.config
    registry = {
        "pg_tables": {
            "label": "PG2PG table definitions (pg_tables.json)",
            "path": cfg["PG_TABLES_JSON_PATH"],
        },
    }
    for category, path in cfg["ADLS_CONF_PATHS"].items():
        registry[f"adls_{category}"] = {
            "label": f"ADLS2ADLS {category} config (adls_{category}.conf)",
            "path": path,
        }
    return registry


@admin_bp.route("/configs")
@login_required
@admin_required
def list_configs():
    registry = _config_registry()
    return render_template("admin/list_configs.html", registry=registry)


@admin_bp.route("/configs/<key>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_config(key):
    registry = _config_registry()
    if key not in registry:
        abort(404)
    entry = registry[key]

    if request.method == "POST":
        text = request.form.get("content", "")
        try:
            write_raw_text(entry["path"], text)
        except ValueError as exc:
            flash(f"Invalid JSON — not saved: {exc}", "danger")
            return render_template("admin/edit_config.html", key=key, entry=entry, content=text)
        flash(f"Saved {entry['label']}.", "success")
        return redirect(url_for("admin.edit_config", key=key))

    content = read_raw_text(entry["path"])
    return render_template("admin/edit_config.html", key=key, entry=entry, content=content)
