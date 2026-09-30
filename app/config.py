"""
Application configuration.

Two application instances share this exact codebase (see run_prod_preprod.py and
run_preprod_dev.py). Each instance is configured with a distinct APP_MODE which
controls: which config files it reads, which environment pairs it is allowed to
operate on, its HTTP port, and its display branding. This keeps the two
deployments as genuinely separate processes/ports (per the requirement) while
avoiding duplicated business logic.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DATA_DIR = BASE_DIR / "config_data"


class BaseConfig:
    # NOTE: each app instance's default differs so that, purely as a local-dev
    # safety net, a session cookie for one console can't be replayed against
    # the other (browser cookies aren't port-scoped, only domain-scoped, and
    # both consoles run on 127.0.0.1). In every real deployment this MUST come
    # from a distinct per-instance k8s Secret via the SECRET_KEY env var.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'data_copy_app.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TIMEOUT_SECONDS = int(os.environ.get("SESSION_TIMEOUT_SECONDS", 5 * 60))
    PERMANENT_SESSION_LIFETIME_SECONDS = int(
        os.environ.get("SESSION_TIMEOUT_SECONDS", 5 * 60)
    )
    DATABRICKS_CONFIG_PATH = os.environ.get(
        "DATABRICKS_CONFIG_PATH", str(CONFIG_DATA_DIR / "databricks_config.yaml")
    )
    # When true (default for local/dev), Spark/Databricks job submission is
    # simulated with a background thread so the UI/dashboard can be exercised
    # without a real Databricks workspace. Set to "0" against a real workspace.
    DATABRICKS_SIMULATE = os.environ.get("DATABRICKS_SIMULATE", "1") == "1"


class ProdPreprodConfig(BaseConfig):
    """Application instance: PROD -> PREPROD data copy."""

    APP_MODE = "prod_preprod"
    APP_TITLE = "Data Copy Console — PROD → PREPROD"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-prod-preprod-change-me")
    # Distinct cookie name so both consoles can be logged into simultaneously
    # from the same browser on localhost (cookies are domain-scoped, not
    # port-scoped) without one login clobbering the other's cookie.
    SESSION_COOKIE_NAME = "dcc_prod_preprod_session"
    SOURCE_ENV = "PROD"
    # Single fixed target for this app instance.
    ALLOWED_TARGET_ENVS = ["PREPROD"]
    PG_TABLES_JSON_PATH = os.environ.get(
        "PG_TABLES_JSON_PATH", str(CONFIG_DATA_DIR / "pg_tables_prod_preprod.json")
    )
    ADLS_CONF_PATHS = {
        "inplace": str(CONFIG_DATA_DIR / "adls_inplace_prod_preprod.conf"),
        "point2point": str(CONFIG_DATA_DIR / "adls_point2point_prod_preprod.conf"),
        "output": str(CONFIG_DATA_DIR / "adls_output_prod_preprod.conf"),
    }
    PORT = int(os.environ.get("PORT", 5001))


class PreprodDevConfig(BaseConfig):
    """Application instance: PREPROD -> DEV (and DEV_env1..4) data copy."""

    APP_MODE = "preprod_dev"
    APP_TITLE = "Data Copy Console — PREPROD → DEV"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-preprod-dev-change-me")
    SESSION_COOKIE_NAME = "dcc_preprod_dev_session"
    SOURCE_ENV = "PREPROD"
    # Multiple candidate dev targets; user picks one per request.
    ALLOWED_TARGET_ENVS = ["DEV", "DEV_env1", "DEV_env2", "DEV_env3", "DEV_env4"]
    PG_TABLES_JSON_PATH = os.environ.get(
        "PG_TABLES_JSON_PATH", str(CONFIG_DATA_DIR / "pg_tables_preprod_dev.json")
    )
    ADLS_CONF_PATHS = {
        "inplace": str(CONFIG_DATA_DIR / "adls_inplace_preprod_dev.conf"),
        "point2point": str(CONFIG_DATA_DIR / "adls_point2point_preprod_dev.conf"),
        "output": str(CONFIG_DATA_DIR / "adls_output_preprod_dev.conf"),
    }
    PORT = int(os.environ.get("PORT", 5002))


CONFIG_BY_MODE = {
    "prod_preprod": ProdPreprodConfig,
    "preprod_dev": PreprodDevConfig,
}
