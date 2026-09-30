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

The original spec's `copy_id` / `audit_logs` fields are implemented here
as `copy_id` / `audit_logs` (see `docs/DESIGN.md` §1) — the numeric prefix
looked like a redaction artifact rather than an intentional identifier.

## Application glimps 

login page for preprod to dev -
<img width="866" height="455" alt="image" src="https://github.com/user-attachments/assets/f162484b-faae-41aa-bc8a-0e81d36e2831" />

Dashboard showing previous data copy requests and active data copies -
<img width="899" height="434" alt="image" src="https://github.com/user-attachments/assets/b882030a-7f66-4490-9036-17d0c65363fa" />

New data copy request - 
<img width="804" height="383" alt="image" src="https://github.com/user-attachments/assets/fdf95092-9985-4805-b588-4866a9df45c9" />

workflow allows to select pg to pg copy -
<img width="902" height="356" alt="image" src="https://github.com/user-attachments/assets/d6679351-a9d4-4187-a177-5bde826f5919" />
if a table is selected, it pops up many option to customize the copy operation, like custom filters, copy mode (overwrite, append), masking with different alogrithms
<img width="683" height="435" alt="image" src="https://github.com/user-attachments/assets/e8f893ba-951e-4c55-b095-9a2c966044c4" />

optionally you can select ADLS copy, with various copy options -
<img width="815" height="367" alt="image" src="https://github.com/user-attachments/assets/d01a398b-a9a5-413d-9e76-84bb480fd069" />
<img width="782" height="373" alt="image" src="https://github.com/user-attachments/assets/3584e2e4-f36c-4d49-9d20-d88dfb029cb1" />

data copy request summary before submitting the copy request -
<img width="866" height="413" alt="image" src="https://github.com/user-attachments/assets/356a53ce-02f9-43d3-bb4d-f501bed5be42" />

Dashboard showing progress status -

<img width="890" height="416" alt="image" src="https://github.com/user-attachments/assets/4ef9937d-3520-4319-8c5d-7a3b1574031e" />
<img width="863" height="258" alt="image" src="https://github.com/user-attachments/assets/95c7ca76-0cf3-4220-8172-4fde997ae18d" />
















