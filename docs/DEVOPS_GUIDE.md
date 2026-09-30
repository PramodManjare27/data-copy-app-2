# Data Copy Console — DevOps / Kubernetes Guide

Audience: platform/DevOps engineers deploying and operating the two console
instances. Application design context lives in `docs/DESIGN.md`; end-user
behavior in `docs/USER_GUIDE.md`.

## 1. What you're deploying

One container image, two independent `Deployment`/`Service` pairs:

| Deployment | Port | Config source | DB target (example) |
|---|---|---|---|
| `dcc-prod-preprod` | 5001 | `pg_tables_prod_preprod.json` + `adls_*_prod_preprod.conf` | Preprod Postgres |
| `dcc-preprod-dev` | 5002 | `pg_tables_preprod_dev.json` + `adls_*_preprod_dev.conf` | Dev Postgres |

Manifests are under `k8s/`. They assume Azure (AKS + Azure Files CSI +
Azure Workload Identity + Azure Databricks) since the spec's ADLS/`abfss://`
paths and UAMI/SP auth modes are Azure-specific; swap the storage class,
identity mechanism, and ingress annotations if you're on a different cloud.

## 2. Build & push the image

```bash
docker build -t <YOUR_REGISTRY>/data-copy-console:<tag> .
docker push <YOUR_REGISTRY>/data-copy-console:<tag>
```

Update the `image:` field in both `k8s/deployment-*.yaml` (or template it in
your CI/CD pipeline / Helm chart — this repo ships plain manifests to stay
tool-agnostic).

## 3. Postgres

Both app instances share one logical database (auth + audit tables) by
default — `AuditLog.app_mode` distinguishes which console produced each row.
This is a deliberate choice: a single audit trail across both hops (prod→
preprod→dev) is more useful than two disjoint ones. If your compliance
posture requires physically separate databases per environment pair instead,
just point `DATABASE_URL` at two different instances — the schema is
identical either way.

- Tables are created automatically on startup via `db.create_all()`
  (`app/__init__.py`). This is fine for this app's two simple tables; if you
  extend the schema, introduce Alembic migrations rather than relying on
  `create_all()` going forward.
- Provision the database and an app-specific role with `CREATE`/`SELECT`/
  `INSERT`/`UPDATE` on its own schema before first deploy — do **not** use
  a superuser credential in `DATABASE_URL`.
- Seed at least one admin user before go-live: run
  `python scripts/seed_db.py` (edit `DEMO_USERS` first, or wire it to your
  own user-provisioning process — this script is a starting point, not a
  production user-management tool).

## 4. Config files: why they're on a PVC, not a ConfigMap

The Admin screen in the app writes directly to `pg_tables_*.json` and the
`adls_*.conf` files on disk. A Kubernetes `ConfigMap` volume mount is
**read-only** inside a pod, so it cannot back that feature.

The manifests instead use:
- A `PersistentVolumeClaim` (`k8s/pvc.yaml`) — `ReadWriteMany`, e.g. Azure
  Files — mounted at `/app/config_data`, which is what the app actually
  reads/writes at runtime.
- A `ConfigMap` per app instance (`dcc-prod-preprod-config-seed`,
  `dcc-preprod-dev-config-seed`) built from this repo's `config_data/*`
  files — i.e. your GitOps source of truth for the *initial* state.
- An `initContainer` (`seed-config`, already wired into both Deployments)
  that copies the ConfigMap's files into the PVC **only if the PVC is
  currently empty**, so redeploys never clobber live admin edits.

Create the seed ConfigMaps once per environment, e.g.:

```bash
kubectl create configmap dcc-prod-preprod-config-seed \
  -n data-copy-console \
  --from-file=config_data/pg_tables_prod_preprod.json \
  --from-file=config_data/adls_inplace_prod_preprod.conf \
  --from-file=config_data/adls_point2point_prod_preprod.conf \
  --from-file=config_data/adls_output_prod_preprod.conf \
  --from-file=config_data/databricks_config.yaml

kubectl create configmap dcc-preprod-dev-config-seed \
  -n data-copy-console \
  --from-file=config_data/pg_tables_preprod_dev.json \
  --from-file=config_data/adls_inplace_preprod_dev.conf \
  --from-file=config_data/adls_point2point_preprod_dev.conf \
  --from-file=config_data/adls_output_preprod_dev.conf \
  --from-file=config_data/databricks_config.yaml
```

If you'd rather config changes always flow through Git review instead of the
in-app editor, that's a valid alternative operating model: disable/hide the
Admin blueprint (comment out its registration in `app/__init__.py`) and
manage config purely via ConfigMap + `kubectl rollout restart` on change.

## 5. Deploy order

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccounts.yaml       # after editing client-id/tenant-id
kubectl apply -f k8s/secret-template.yaml       # after replacing REPLACE_ME values (or use your secret manager)
kubectl create configmap ...                    # see §4
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment-prod-preprod.yaml
kubectl apply -f k8s/deployment-preprod-dev.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/ingress.yaml               # after editing hostnames/TLS
```

Verify:

```bash
kubectl -n data-copy-console get pods
kubectl -n data-copy-console logs deploy/dcc-prod-preprod
```

Both readiness/liveness probes hit `GET /auth/login` (a cheap, always-200
route once the app + DB connection are healthy).

## 6. Databricks connectivity

- **Auth mode `uami`** (recommended): the pod's `ServiceAccount` is federated
  to an Azure User-Assigned Managed Identity via Azure AD Workload Identity
  (`k8s/serviceaccounts.yaml` has the annotations; requires the Workload
  Identity webhook installed on the cluster and the identity granted access
  to the Databricks workspace). No secret material to rotate.
- **Auth mode `sp`**: set `auth_mode: sp` in `databricks_config.yaml` and
  populate the `service_principal` block's `tenant_id`/`client_id`; the
  matching secret goes in `DATABRICKS_SP_CLIENT_SECRET` (already wired as an
  env var from the per-instance Secret in both Deployments).
- Real job submission (`DatabricksClient._submit_real`,
  `_get_uami_token`/`_get_sp_token`) is stubbed with clear `NotImplementedError`
  markers in `app/databricks_client.py` — wiring these to your workspace's
  Jobs API is expected infra work before go-live. Set
  `DATABRICKS_SIMULATE=0` once that's done (both Deployments already default
  to `0`; local/dev runs default to `1`).
- Network: the pods need egress to your Databricks workspace URL (and to
  Postgres). If the cluster enforces default-deny egress via
  `NetworkPolicy`, add explicit allow rules for both destinations per
  namespace.

## 7. Security hardening checklist

- [ ] `SECRET_KEY`, `DATABASE_URL`, `MASKING_HMAC_SALT`,
      `DATABRICKS_SP_CLIENT_SECRET` are **distinct** values per app instance,
      sourced from your secret manager (Key Vault + CSI driver, External
      Secrets Operator, Sealed Secrets) — never committed to Git.
      `k8s/secret-template.yaml` is a template only, not real secrets.
- [ ] Containers run as non-root (already set: `runAsNonRoot: true`,
      dedicated `appuser` in the Dockerfile).
- [ ] Network policy restricts `dcc-prod-preprod` and `dcc-preprod-dev` from
      reaching each other's Postgres/Databricks targets if you choose the
      physically-separate-database model from §3.
- [ ] TLS terminated at the ingress (`k8s/ingress.yaml` assumes
      cert-manager); never expose either console over plain HTTP externally,
      since login credentials and JDBC connection strings pass over it.
- [ ] Rotate `SECRET_KEY` on a schedule — this invalidates all active
      sessions, so plan for a maintenance window or a rolling secret with
      grace-period support if that matters to your users.
- [ ] Restrict the `admin` role deliberately — anyone with it can rewrite
      which tables/locations are copyable and how they're masked.

## 8. Scaling & operations

- Both Deployments start at 2 replicas with an HPA scaling to 6 on 70% CPU
  (`k8s/hpa.yaml`) — the app itself is stateless per-request (session state
  lives in the signed cookie; the wizard draft lives server-side in the
  session too, so **enable sticky sessions at the ingress/load-balancer** if
  you run more than 1 replica, or the multi-step wizard will break when a
  user's requests land on different pods mid-flow). On nginx-ingress, add:
  ```
  nginx.ingress.kubernetes.io/affinity: "cookie"
  nginx.ingress.kubernetes.io/session-cookie-name: "dcc-affinity"
  ```
- The actual Spark/Databricks jobs run on Databricks compute, not in these
  pods — the Flask pods only submit jobs and poll/update audit rows, so pod
  CPU/memory needs are modest (requests/limits in the manifests are a
  reasonable starting point; tune from observed usage).
- Gunicorn runs 4 sync workers per pod by default (see Dockerfile CMD /
  Deployment `command`) — increase `--workers` or replicas if login/dashboard
  latency becomes a bottleneck under load; this is a low-traffic internal
  tool by nature, so the defaults should comfortably cover most teams.

## 9. Local development (for comparison)

```bash
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python scripts/seed_db.py
python run_prod_preprod.py    # http://localhost:5001
python run_preprod_dev.py     # http://localhost:5002, separate terminal
```

Local runs default to SQLite (`instance/data_copy_app.db`) and
`DATABRICKS_SIMULATE=1` so the full UI/dashboard/audit flow can be exercised
without any real Postgres/Databricks/ADLS access — override `DATABASE_URL`
and `DATABRICKS_SIMULATE=0` to point at real infrastructure once available.

## 10. Runbook: common failure modes

| Symptom | Where to look |
|---|---|
| Pod `CrashLoopBackOff` | `kubectl logs` — almost always a bad/missing `DATABASE_URL` or the DB being unreachable from the cluster network |
| Everyone logged out at once | `SECRET_KEY` changed/rotated (expected — sessions are stateless and signed) |
| Wizard state disappears mid-flow with 2+ replicas | Missing sticky-session ingress annotation (§8) |
| Admin's config edit doesn't show up for other users | Check the edit actually targeted the PVC-backed path and not a stale ConfigMap mount — confirm with `kubectl exec ... -- cat /app/config_data/<file>` |
| All jobs stuck at `QUEUED` forever | `DATABRICKS_SIMULATE=1` accidentally left set in a real environment (jobs never actually "run" — the simulator background thread is per-pod, per-process, so this also breaks across restarts) |
| Databricks submission fails immediately | `_submit_real`/`_get_uami_token`/`_get_sp_token` in `app/databricks_client.py` are integration stubs — confirm they've been implemented against your workspace before disabling simulate mode |
