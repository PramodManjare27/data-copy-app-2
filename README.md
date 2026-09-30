# Data Copy Console

Two Flask consoles for auditable, masked data copies between environments,
executed as Spark jobs on Databricks:

- **PROD → PREPROD** (port 5001) — `run_prod_preprod.py`
- **PREPROD → DEV / DEV_env1-4** (port 5002) — `run_preprod_dev.py`

Both support **PG2PG** (PostgreSQL table copy via Spark JDBC) and
**ADLS2ADLS** (ADLS Gen2 location copy, in `inplace` / `point2point` /
`output` sub-categories) in one guided, skippable wizard, with column
masking, per-request filters, and a live dashboard/audit trail.

Full documentation:
- [docs/DESIGN.md](docs/DESIGN.md) — architecture, data model, config formats, masking, Databricks integration
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — how to use the wizard and dashboard
- [docs/DEVOPS_GUIDE.md](docs/DEVOPS_GUIDE.md) — Kubernetes deployment, secrets, scaling, runbook

## Quick start (local)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
python scripts/seed_db.py       # creates demo users (prints credentials)

python run_prod_preprod.py      # terminal 1 -> http://localhost:5001
python run_preprod_dev.py       # terminal 2 -> http://localhost:5002
```

Local runs default to SQLite and a simulated Databricks job runner
(`DATABRICKS_SIMULATE=1`) so the full wizard → submit → live progress →
audit trail flow works out of the box with no external dependencies. See
`docs/DEVOPS_GUIDE.md` for pointing this at real Postgres/Databricks and
deploying to Kubernetes.

## Project layout

```
app/
  auth/          login, logout, session-timeout enforcement
  pg2pg/         PG2PG wizard step
  adls2adls/     ADLS2ADLS wizard step
  dashboard/     home dashboard, new-request/summary/submit, refresh API
  admin/         config file editor (admin role only)
  models.py      auth_users, audit_logs
  masking.py     standard masking algorithms
  config_loader.py   pg_tables*.json / adls_*.conf readers+writers
  databricks_client.py   job submission (simulated locally, real stubs for prod)
  templates/, static/
config_data/     seed PG table defs, ADLS conf files, databricks_config.yaml
k8s/             Deployment/Service/PVC/Secret-template/Ingress/HPA manifests
docs/            DESIGN.md, USER_GUIDE.md, DEVOPS_GUIDE.md
scripts/         seed_db.py, generate_adls_conf.py (one-off seed generator)
```

## Naming note

The original spec's `16_copy_id` / `16_audit_logs` fields are implemented here
as `copy_id` / `audit_logs` (see `docs/DESIGN.md` §1) — the numeric prefix
looked like a redaction artifact rather than an intentional identifier.
