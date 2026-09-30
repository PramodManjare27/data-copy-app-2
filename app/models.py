"""
Database models.

- User: authentication table (PostgreSQL in production; see docs/DEVOPS_GUIDE.md).
- AuditLog: one row per (table / adls-location) copied, per submitted request.
  A single UI submission that covers several tables/locations produces several
  AuditLog rows sharing the same request_group_id, so the dashboard can show a
  request's overall progress as well as per-item detail.
"""
import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """Authentication table. Lives in Postgres in every real deployment."""

    __tablename__ = "auth_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # user | admin
    is_active_flag = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    # Flask-Login expects `is_active` to be a property/attribute.
    @property
    def is_active(self):  # noqa: D401 - required by UserMixin contract
        return self.is_active_flag


class AuditLog(db.Model):
    """Audit trail for every data-copy item that is triggered."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    request_group_id = db.Column(
        db.String(36), nullable=False, default=lambda: str(uuid.uuid4()), index=True
    )

    app_mode = db.Column(db.String(20), nullable=False)  # prod_preprod | preprod_dev
    copy_type = db.Column(db.String(20), nullable=False)  # pg2pg | adls2adls
    adls_category = db.Column(db.String(20), nullable=True)  # inplace|point2point|output
    copy_id = db.Column(db.String(120), nullable=True)

    triggered_by = db.Column(db.String(80), nullable=False)

    source_env = db.Column(db.String(30), nullable=False)
    target_env = db.Column(db.String(30), nullable=False)

    source_object = db.Column(db.String(500), nullable=False)  # table or ADLS path
    target_object = db.Column(db.String(500), nullable=False)  # table or ADLS path

    mode = db.Column(db.String(20), nullable=True)  # append | reload / overwrite
    filter_condition = db.Column(db.Text, nullable=True)
    masked_columns = db.Column(db.Text, nullable=True)  # JSON-encoded list/dict
    masking_algorithm = db.Column(db.String(60), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="QUEUED")
    # QUEUED | IN_PROGRESS | SUCCESS | FAILED
    progress_pct = db.Column(db.Integer, nullable=False, default=0)

    start_time = db.Column(db.DateTime(timezone=True), nullable=True)
    end_time = db.Column(db.DateTime(timezone=True), nullable=True)
    expected_eta_seconds = db.Column(db.Integer, nullable=True)

    databricks_run_id = db.Column(db.String(80), nullable=True)
    error_description = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "request_group_id": self.request_group_id,
            "app_mode": self.app_mode,
            "copy_type": self.copy_type,
            "adls_category": self.adls_category,
            "copy_id": self.copy_id,
            "triggered_by": self.triggered_by,
            "source_env": self.source_env,
            "target_env": self.target_env,
            "source_object": self.source_object,
            "target_object": self.target_object,
            "mode": self.mode,
            "filter_condition": self.filter_condition,
            "masked_columns": self.masked_columns,
            "masking_algorithm": self.masking_algorithm,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "expected_eta_seconds": self.expected_eta_seconds,
            "databricks_run_id": self.databricks_run_id,
            "error_description": self.error_description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
