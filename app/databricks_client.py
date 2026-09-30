"""
Databricks Jobs submission client.

Every data-copy request is executed as a Spark job on Databricks (JDBC
read/write for PG2PG, Spark-native ADLS Gen2 reads/writes for ADLS2ADLS).
Authentication to the Databricks workspace is externalized to
config_data/databricks_config.yaml and supports two modes:

  * uami - User-Assigned Managed Identity (recommended when the app itself
    runs on Azure/AKS: no secret material to manage, token obtained from the
    Azure Instance Metadata Service).
  * sp   - Service Principal (client id / client secret via OAuth2 client
    credentials grant against Azure AD) - used when the app runs somewhere
    without managed identity support.

For local development / this demo, DATABRICKS_SIMULATE=1 (the default) skips
real network calls entirely and instead runs a lightweight background thread
that mimics a Spark job's lifecycle (QUEUED -> IN_PROGRESS -> SUCCESS/FAILED)
so the dashboard's progress bars and audit trail behave realistically without
a live Databricks workspace or ADLS/Postgres credentials.
"""
from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml


def load_databricks_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class DatabricksAuthError(RuntimeError):
    pass


def _get_uami_token(cfg: Dict[str, Any]) -> str:
    """Would call http://169.254.169.254/metadata/identity/oauth2/token on Azure.
    Stubbed here; real implementation left as an infra integration point."""
    raise NotImplementedError(
        "UAMI token acquisition requires running on Azure infrastructure with "
        "the managed identity attached. Configure DATABRICKS_SIMULATE=1 for "
        "local development, or implement _get_uami_token for your platform."
    )


def _get_sp_token(cfg: Dict[str, Any]) -> str:
    """Would perform an OAuth2 client-credentials call to Azure AD using
    client_id/client_secret/tenant_id from the service_principal config
    block. Stubbed here; real implementation left as an infra integration
    point (avoid hardcoding secrets - source them from a k8s Secret)."""
    raise NotImplementedError(
        "Service Principal token acquisition is not wired to a live Azure AD "
        "tenant in this build. Configure DATABRICKS_SIMULATE=1 for local "
        "development, or implement _get_sp_token."
    )


class DatabricksClient:
    def __init__(self, config_path: str, simulate: bool = True):
        self.config = load_databricks_config(config_path)
        self.simulate = simulate

    def _get_token(self) -> str:
        auth_mode = (self.config.get("auth_mode") or "uami").lower()
        if auth_mode == "uami":
            return _get_uami_token(self.config)
        if auth_mode == "sp":
            return _get_sp_token(self.config)
        raise DatabricksAuthError(f"Unsupported auth_mode: {auth_mode}")

    def submit_copy_job(self, audit_log_id: int, app) -> str:
        """Submits (or simulates) a Spark job for one AuditLog row.

        Returns a Databricks run id immediately (async submission) and, in
        simulate mode, spawns a background thread that advances the row's
        status/progress over time exactly like a real job would be observed
        via periodic polling of the Jobs API.
        """
        run_id = f"sim-{uuid.uuid4().hex[:10]}" if self.simulate else self._submit_real(audit_log_id)

        if self.simulate:
            thread = threading.Thread(
                target=self._simulate_job,
                args=(audit_log_id, run_id, app),
                daemon=True,
            )
            thread.start()
        return run_id

    def _submit_real(self, audit_log_id: int) -> str:
        """Real integration point: POST to
        {workspace_url}/api/2.1/jobs/runs/submit with a spark_python_task /
        notebook_task that carries the copy parameters (source/target JDBC
        or ADLS paths, filter, masking spec, mode) and the cluster spec from
        databricks_config.yaml. Requires `requests` + a valid bearer token
        from _get_token(). Left unimplemented for this environment."""
        raise NotImplementedError(
            "Real Databricks submission is not enabled in this build. Set "
            "DATABRICKS_SIMULATE=1 (default) for local/demo use, or "
            "implement _submit_real against your workspace."
        )

    def _simulate_job(self, audit_log_id: int, run_id: str, app):
        from app.extensions import db
        from app.models import AuditLog

        with app.app_context():
            row = db.session.get(AuditLog, audit_log_id)
            if row is None:
                return
            row.status = "IN_PROGRESS"
            row.start_time = datetime.now(timezone.utc)
            row.databricks_run_id = run_id
            row.expected_eta_seconds = random.randint(20, 45)
            db.session.commit()

        total_ticks = random.randint(6, 10)
        should_fail = random.random() < 0.08  # occasional simulated failure for realism
        fail_at_tick = random.randint(2, total_ticks - 1) if should_fail else None

        for tick in range(1, total_ticks + 1):
            time.sleep(random.uniform(1.2, 2.2))
            with app.app_context():
                row = db.session.get(AuditLog, audit_log_id)
                if row is None:
                    return
                if fail_at_tick and tick >= fail_at_tick:
                    row.status = "FAILED"
                    row.progress_pct = min(99, int(tick / total_ticks * 100))
                    row.end_time = datetime.now(timezone.utc)
                    row.error_description = (
                        "Spark job failed: JDBC write timed out while flushing "
                        "partition batch to target (simulated failure for demo)."
                    )
                    db.session.commit()
                    return
                row.progress_pct = int(tick / total_ticks * 100)
                db.session.commit()

        with app.app_context():
            row = db.session.get(AuditLog, audit_log_id)
            if row is None:
                return
            row.status = "SUCCESS"
            row.progress_pct = 100
            row.end_time = datetime.now(timezone.utc)
            db.session.commit()


def get_client(config) -> DatabricksClient:
    return DatabricksClient(
        config_path=config["DATABRICKS_CONFIG_PATH"],
        simulate=config["DATABRICKS_SIMULATE"],
    )
