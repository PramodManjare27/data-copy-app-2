import time
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        # Validate against the auth_users table; do not reveal which part
        # (username vs. password) was wrong.
        if user is None or not user.is_active_flag or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html"), 401

        login_user(user)
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        session["last_active_at"] = time.time()
        session.permanent = True
        flash(f"Welcome back, {user.username}.", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.home"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
