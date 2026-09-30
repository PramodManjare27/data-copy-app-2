import json
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import AuditLog
from app.databricks_client import get_client
from app.wizard_state import get_draft, new_draft, clear_draft

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

ACTIVE_STATUSES = ("QUEUED", "IN_PROGRESS")


@dashboard_bp.route("/")
@login_required
def home():
    active = (
        AuditLog.query.filter(AuditLog.status.in_(ACTIVE_STATUSES))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()
    return render_template("dashboard/home.html", active=active, recent=recent)


@dashboard_bp.route("/api/audit-logs")
@login_required
def api_audit_logs():
    """Backs the dashboard's Refresh button and the active-jobs poller."""
    active = (
        AuditLog.query.filter(AuditLog.status.in_(ACTIVE_STATUSES))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()
    return jsonify({
        "active": [a.to_dict() for a in active],
        "recent": [r.to_dict() for r in recent],
    })


@dashboard_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_request():
    allowed_targets = current_app.config["ALLOWED_TARGET_ENVS"]

    if request.method == "POST":
        target_env = request.form.get("target_env")
        if target_env not in allowed_targets:
            flash("Please choose a valid target environment.", "danger")
            return redirect(url_for("dashboard.new_request"))
        new_draft(target_env)
        return redirect(url_for("pg2pg.configure"))

    # Single fixed target (prod_preprod) skips the picker entirely.
    if len(allowed_targets) == 1:
        new_draft(allowed_targets[0])
        return redirect(url_for("pg2pg.configure"))

    existing_draft = get_draft()
    current_target_env = existing_draft.get("target_env") if existing_draft else None

    return render_template(
        "dashboard/new_request.html",
        allowed_targets=allowed_targets,
        current_target_env=current_target_env,
    )


@dashboard_bp.route("/summary", methods=["GET"])
@login_required
def summary():
    draft = get_draft()
    if not draft:
        flash("Start a new copy request first.", "warning")
        return redirect(url_for("dashboard.new_request"))
    if not draft.get("pg_items") and not draft.get("adls_items"):
        flash("Select at least one PG2PG table or ADLS2ADLS location before continuing.", "warning")
        return redirect(url_for("pg2pg.configure"))
    return render_template("dashboard/summary.html", draft=draft)


@dashboard_bp.route("/submit", methods=["POST"])
@login_required
def submit():
    draft = get_draft()
    if not draft or (not draft.get("pg_items") and not draft.get("adls_items")):
        flash("Nothing to submit.", "danger")
        return redirect(url_for("dashboard.new_request"))

    app_mode = current_app.config["APP_MODE"]
    target_env_default = draft["target_env"]
    source_env_default = current_app.config["SOURCE_ENV"]

    created_rows = []
    request_group_id = None

    for item in draft.get("pg_items", []):
        row = AuditLog(
            app_mode=app_mode,
            copy_type="pg2pg",
            copy_id=item.get("copy_id"),
            triggered_by=current_user.username,
            source_env=source_env_default,
            target_env=target_env_default,
            source_object=item.get("source_table"),
            target_object=item.get("target_table"),
            mode=item.get("mode"),
            filter_condition=item.get("filter_condition") or None,
            masked_columns=json.dumps(item.get("masked_columns") or []),
            masking_algorithm=item.get("masking_algorithm"),
            status="QUEUED",
            progress_pct=0,
        )
        if request_group_id:
            row.request_group_id = request_group_id
        db.session.add(row)
        db.session.flush()
        request_group_id = row.request_group_id
        created_rows.append(row)

    for item in draft.get("adls_items", []):
        custom_filters = {
            "partitioned_column": item.get("partitioned_column"),
            "partition_column_format": item.get("partition_column_format"),
            "additional_filter": item.get("additional_filter"),
            "masking_columns": item.get("masking_columns"),
        }
        row = AuditLog(
            app_mode=app_mode,
            copy_type="adls2adls",
            adls_category=item.get("category"),
            copy_id=item.get("source_lens_name"),
            triggered_by=current_user.username,
            source_env=source_env_default,
            target_env=target_env_default,
            source_object=item.get("source_adls_location"),
            target_object=item.get("target_adls_location"),
            mode=item.get("target_clean_up"),
            filter_condition=json.dumps(custom_filters),
            masked_columns=json.dumps(item.get("masking_columns") or []),
            masking_algorithm=item.get("masking_algorithm"),
            status="QUEUED",
            progress_pct=0,
        )
        if request_group_id:
            row.request_group_id = request_group_id
        db.session.add(row)
        db.session.flush()
        request_group_id = row.request_group_id
        created_rows.append(row)

    db.session.commit()

    client = get_client(current_app.config)
    flask_app = current_app._get_current_object()
    for row in created_rows:
        client.submit_copy_job(row.id, flask_app)

    clear_draft()
    flash(f"Submitted {len(created_rows)} data copy item(s) to Databricks.", "success")
    return redirect(url_for("dashboard.home"))
