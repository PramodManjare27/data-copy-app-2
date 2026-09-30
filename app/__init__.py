"""Application factory shared by both the prod_preprod and preprod_dev instances."""
import json
import time
from datetime import timedelta
from pathlib import Path

from flask import Flask, session, redirect, url_for, flash, request
from flask_login import current_user, logout_user

from app.config import BASE_DIR, CONFIG_BY_MODE
from app.extensions import db, login_manager


def create_app(app_mode: str) -> Flask:
    if app_mode not in CONFIG_BY_MODE:
        raise ValueError(f"Unknown app_mode '{app_mode}', expected one of {list(CONFIG_BY_MODE)}")

    Path(BASE_DIR / "instance").mkdir(exist_ok=True)

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_MODE[app_mode])
    app.permanent_session_lifetime = timedelta(
        seconds=app.config["PERMANENT_SESSION_LIFETIME_SECONDS"]
    )

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Blueprints ---------------------------------------------------
    from app.auth.routes import auth_bp
    from app.pg2pg.routes import pg2pg_bp
    from app.adls2adls.routes import adls2adls_bp
    from app.dashboard.routes import dashboard_bp
    from app.admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pg2pg_bp)
    app.register_blueprint(adls2adls_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.home"))
        return redirect(url_for("auth.login"))

    @app.template_filter("fromjson")
    def fromjson_filter(value):
        if not value:
            return []
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return []

    @app.context_processor
    def inject_globals():
        return {
            "app_title": app.config["APP_TITLE"],
            "app_mode": app.config["APP_MODE"],
            "source_env": app.config["SOURCE_ENV"],
        }

    # --- Idle-session auto logout (5 minutes of inactivity, configurable) ---
    EXEMPT_ENDPOINTS = {"auth.login", "static"}

    @app.before_request
    def enforce_session_timeout():
        if not current_user.is_authenticated:
            return None
        if request.endpoint in EXEMPT_ENDPOINTS:
            return None

        timeout = app.config["SESSION_TIMEOUT_SECONDS"]
        now = time.time()
        last_active = session.get("last_active_at")

        if last_active is not None and (now - last_active) > timeout:
            logout_user()
            session.clear()
            flash("You were signed out after 5 minutes of inactivity.", "warning")
            return redirect(url_for("auth.login"))

        session["last_active_at"] = now
        session.permanent = True
        return None

    with app.app_context():
        db.create_all()

    return app
