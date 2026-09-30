# Data Copy Console — Design Document

## 1. Purpose

Two web consoles that let authorized users trigger, mask, filter, and audit
bulk data copies between environments:

| App instance   | Source  | Target(s)                              | Default port |
|----------------|---------|-----------------------------------------|---------------|
| `prod_preprod` | `PROD`  | `PREPROD`                               | 5001 |
| `preprod_dev`  | `PREPROD` | `DEV`, `DEV_env1`, `DEV_env2`, `DEV_env3`, `DEV_env4` | 5002 |

Each instance supports two independent copy mechanisms, either or both of
which a user may select in a single request:

- **PG2PG** — PostgreSQL table-to-table copy via Spark JDBC, executed on Databricks.
- **ADLS2ADLS** — Azure Data Lake Storage Gen2 location-to-location copy via
  Spark, in three sub-categories: `inplace`, `point2point`, `output`.

> **Naming note:** the original spec used field/table names `16_copy_id` and
> `16_audit_logs`. That numeric prefix is assumed to be an artifact of the
> source document (e.g. a redacted project codename) rather than an
> intentional identifier, since it is not valid as a stable JSON/Python
> convention on its own. This build uses `copy_id` and `audit_logs`. Renaming
> is a single find-and-replace across `app/models.py`, `app/config_loader.py`,
> and the templates if the prefix was in fact intentional.

## 2. Why one codebase, two processes

The requirement is for prod→preprod and preprod→dev to be **separate
applications on separate ports**. Rather than forking the codebase (which
would double the maintenance surface and let the two drift apart), this build
uses the Flask **application factory** pattern: `app/create_app(app_mode)`
builds a fully independent Flask app object per mode, and two thin entry
points (`run_prod_preprod.py`, `run_preprod_dev.py`) each construct one. In
Kubernetes these become two separate `Deployment`/`Service` pairs from the
**same container image**, differing only in command args, env vars, and
mounted config (see `docs/DEVOPS_GUIDE.md`).

Consequences of this choice, by design:

- Each instance has its own `SECRET_KEY`, session cookie name, allowed
  target-environment list, and config file paths (`app/config.py`).
- Each instance is a fully independent process/pod — one crashing, scaling,
  or redeploying never affects the other.
- Business logic (auth, masking, audit, Databricks submission, config
  loading) lives once, under `app/`, imported by both.

## 3. Architecture overview

```
                    ┌───────────────────────┐         ┌───────────────────────┐
                    │  dcc-prod-preprod      │         │  dcc-preprod-dev       │
                    │  (Flask, port 5001)    │         │  (Flask, port 5002)    │
                    └───────────┬───────────┘         └───────────┬───────────┘
                                │                                  │
                   shared code: app/ (auth, pg2pg,                 │
                   adls2adls, dashboard, admin,                    │
                   masking, databricks_client)                     │
                                │                                  │
                    ┌───────────┴──────────────────────────────────┴───────────┐
                    │                     PostgreSQL                           │
                    │   auth_users  |  audit_logs (app_mode distinguishes)     │
                    └───────────────────────────────────────────────────────────┘
                                │                                  │
                    ┌───────────┴───────────┐         ┌────────────┴───────────┐
                    │ pg_tables_prod_       │         │ pg_tables_preprod_     │
                    │ preprod.json          │         │ dev.json               │
                    │ adls_*_prod_preprod   │         │ adls_*_preprod_dev     │
                    │ .conf (x3)            │         │ .conf (x3)             │
                    └───────────────────────┘         └────────────────────────┘
                                │                                  │
                                └───────────────┬──────────────────┘
                                                 │
                                     ┌───────────┴───────────┐
                                     │  Databricks workspace  │
                                     │  (Spark JDBC / ADLS    │
                                     │   copy jobs, UAMI/SP)  │
                                     └────────────────────────┘
```

## 4. Request lifecycle (the wizard)

The UI is a 4-step wizard (`app/wizard_state.py` holds the in-progress draft
in the server-side session — nothing is persisted until final submit):

1. **Target environment** — fixed and auto-selected for `prod_preprod`
   (single target: PREPROD); a picker of 5 options for `preprod_dev`.
2. **PG2PG** *(optional — can be skipped)* — tables are read from
   `pg_tables_*.json`, filtered to entries whose `target_env` matches step 1.
   Per table the user may: rename the target table, edit/override `mode`
   (`append`/`reload`, preprod→dev only), enter a free-text SQL filter
   predicate, and check which columns to mask plus the masking algorithm.
3. **ADLS2ADLS** *(optional — can be skipped, but not both 2 and 3)* — three
   tabs (In-Place / Point-to-Point / Output) list entries from the matching
   `adls_*.conf`, filtered the same way by `target-env`. Per entry the user
   may override `target-clean-up`, partition column/format, and add a
   free-text additional filter. Masking columns come from the conf's
   `customfilters.masking_columns` and are applied automatically — the user
   cannot add new ones here, only see which will be masked and with what
   algorithm — matching the requirement that config-driven masking is
   selective and visible, not ad hoc.
4. **Review & Submit** — a human-readable summary of every selected
   PG2PG/ADLS2ADLS item (table names, filters, masked columns + algorithm,
   modes) before anything is written to the database or sent to Databricks.

On submit (`app/dashboard/routes.py:submit`), one `AuditLog` row is created
**per selected table/location**, all sharing one `request_group_id` (a UUID)
so a multi-item request can be tracked as a group on the dashboard while each
item still gets its own status/progress/error. Each row is then handed to
`DatabricksClient.submit_copy_job`.

## 5. Data model

### `auth_users` (Postgres — `app/models.py::User`)

| column | notes |
|---|---|
| `id` | PK |
| `username` | unique, used to log in |
| `email` | optional |
| `password_hash` | Werkzeug `generate_password_hash` (PBKDF2) |
| `role` | `user` \| `admin` — admins can edit config files |
| `is_active_flag` | soft-disable a user without deleting the row |
| `last_login_at` | updated on every successful login |

Authentication is validated directly against this table on every login
(`app/auth/routes.py`) — no external IdP in this build, though swapping in
SSO/OIDC later only touches `auth/routes.py` and the `User` model stays.

### `audit_logs` (Postgres — `app/models.py::AuditLog`)

One row per table/location per submitted request:

| column | purpose |
|---|---|
| `request_group_id` | groups rows from one wizard submission |
| `app_mode` | `prod_preprod` \| `preprod_dev` — which console created it |
| `copy_type` | `pg2pg` \| `adls2adls` |
| `adls_category` | `inplace` \| `point2point` \| `output` (adls2adls only) |
| `copy_id` | from config (PG2PG) or lens name (ADLS2ADLS) |
| `triggered_by` | username who submitted the request |
| `source_env` / `target_env` | e.g. `PROD` / `PREPROD` |
| `source_object` / `target_object` | table name or ADLS URI |
| `mode` | append/reload (PG2PG) or append/overwrite (ADLS2ADLS clean-up) |
| `filter_condition` | free-text filter the user entered, logged verbatim |
| `masked_columns` | JSON list of column names |
| `masking_algorithm` | which algorithm from `app/masking.py` was used |
| `status` | `QUEUED` → `IN_PROGRESS` → `SUCCESS`/`FAILED` |
| `progress_pct` | 0–100, polled by the dashboard |
| `start_time` / `end_time` / `expected_eta_seconds` | timing |
| `databricks_run_id` | correlates back to the Databricks Jobs UI |
| `error_description` | populated on failure |

This satisfies the audit requirements directly: who, what table, target
table, filter used, masked columns, timestamps, ETA, status, and error
detail — all queryable and rendered on the dashboard.

## 6. Config file formats

### `pg_tables_*.json`

Extends the format given in the spec with a `columns` array, which is
**required** to satisfy "display table name and its columns with their data
types" — the original example JSON had no column metadata, so this was added:

```json
{
  "copy_type": "pg2pg",
  "copy_id": "test1_copy",
  "source_env": "PROD",
  "target_env": "PREPROD",
  "source_table": "gsd.test1",
  "target_table": "gsd.test1",
  "source_jdbc_connection_string": "...",
  "target_jdbc_connection_string": "...",
  "mode": "append",
  "columns": [
    { "name": "email", "type": "varchar(255)", "pii": true }
  ]
}
```

`pii: true` only pre-checks that column's masking checkbox in the UI as a
convenience default — it does not force masking; the user can uncheck it.

For `preprod_dev`, the same `copy_id` appears 5 times (once per `target_env`:
`DEV`, `DEV_env1..4`) exactly as specified, each with its own JDBC string and
`mode`. The wizard filters to the one row matching the environment chosen in
step 1.

### `adls_{inplace,point2point,output}_*.conf`

JSON body (the `.conf` extension is kept purely for the filename convention
requested), one array per file, matching the spec's shape with
`customfilters.masking_columns` driving automatic masking.

### `databricks_config.yaml`

Kept entirely separate from the JSON copy configs, per requirement. Holds:
`workspace_url`, `auth_mode` (`uami` or `sp`), the managed-identity or
service-principal parameters, cluster/job defaults, and a
`performance_tuning` block (see §8).

## 7. Masking

`app/masking.py` implements four standard, named algorithms so the UI can
always show *which* algorithm ran (a hard requirement for ADLS2ADLS, applied
here uniformly to both copy types for consistency):

- **SHA-256 Hash** (default) — deterministic, irreversible, salted HMAC.
- **Partial Mask** — keeps first/last 2 chars, e.g. `jo******oe`.
- **Full Redact** — replaces with a fixed literal.
- **Deterministic Tokenization** — stable `TOK_xxxxxxxx` surrogate.

For PG2PG, the user picks the algorithm per table (applied to every column
checked for that table). For ADLS2ADLS, the algorithm is fixed
(`sha256_hash`) and simply **displayed**, since the masking columns
themselves are config-driven, not user-chosen, per the spec ("user should be
able to see masking algo").

The actual column-value masking runs inside the Spark job on Databricks
(`mask_value()` is also importable there); the web app's job is to decide
*which* columns/algorithm apply and record that decision in the audit log.

## 8. Databricks / Spark integration

`app/databricks_client.py` centralizes job submission. Two real auth modes
are modeled in `databricks_config.yaml` (`uami`, `sp`) with their token
acquisition left as clearly marked integration points (`_get_uami_token`,
`_get_sp_token`, `_submit_real`) — wiring these to a live workspace is an
infra/credentials task outside what this environment can exercise, and is
called out explicitly rather than faked.

For local development and demonstration, `DATABRICKS_SIMULATE=1` (the
default) replaces the real Jobs API call with a background thread that walks
each `AuditLog` row through `QUEUED → IN_PROGRESS → SUCCESS/FAILED` with a
random realistic duration and an occasional simulated failure — this is what
powers the live progress bars during local testing without needing real
Postgres/Databricks/ADLS credentials.

**Spark performance tuning** (`databricks_config.yaml::performance_tuning`,
applied by the Spark job code that runs on Databricks, not by the Flask app
itself):
- PG2PG: tuned JDBC `fetchsize`/`batchsize`, partitioned reads on a
  primary-key/serial column, explicit `READ_COMMITTED` isolation to avoid
  long-held locks on production source tables.
- ADLS2ADLS: Delta `optimizeWrite`/`autoCompact` enabled, target file size
  capped to avoid small-file sprawl, broadcast-join threshold tuned for
  typical lookup-table sizes.

## 9. Authentication & session timeout

- `Flask-Login` backs session auth; `User.check_password` uses
  Werkzeug's salted-hash comparison.
- **Idle timeout**: `app/__init__.py::enforce_session_timeout` is a
  `before_request` hook that stamps `session["last_active_at"]` on every
  authenticated request and force-logs-out (clearing the session) once more
  than `SESSION_TIMEOUT_SECONDS` (default 300s / 5 min) has elapsed since the
  last request. This is the authoritative enforcement — it runs server-side
  on every request regardless of the client.
- `app/static/js/idle-timeout.js` is a client-side *UX mirror only*: it warns
  the user 30s before the timeout and redirects to `/auth/logout` locally, so
  an idle tab doesn't just silently 302 the next time they click something.
  It has no security function on its own.

## 10. Renamed-target-table rule (preprod→dev)

Per requirement: if the user changes the target table name away from the
config default, the wizard forces `mode = append` for that item
(`app/pg2pg/routes.py::configure`) and flags `target_table_renamed = true` on
the draft item, which is surfaced on the review screen ("renamed — new table
will be created"). The actual DDL (`CREATE TABLE ... LIKE source`) is a
responsibility of the Spark copy job on Databricks, driven by this flag in
the job payload — the web app's job is to capture and pass along the intent
correctly, not to run DDL itself.

## 11. Admin config editing vs. Kubernetes

The in-app Admin screens (`app/admin/`) let an `admin`-role user edit the
raw JSON of `pg_tables_*.json` and the three `adls_*.conf` files, with
validation before write. In Kubernetes, this requires the config directory
to be **writable** at runtime — see `docs/DEVOPS_GUIDE.md` §4 for why a plain
`ConfigMap` mount (read-only) doesn't work here and what's used instead
(a seeded, writable PVC).

## 12. Security notes

- Masking HMAC salt (`MASKING_HMAC_SALT`) and `SECRET_KEY` must be distinct
  per environment/app-instance secrets in any real deployment — defaults in
  `app/config.py` are dev-only placeholders.
- JDBC connection strings and Databricks credentials are never rendered in
  the UI beyond the connection string itself (no passwords are stored in
  `pg_tables*.json` in this design — see DEVOPS_GUIDE for where real
  credentials should live, e.g. Databricks secret scopes referenced by the
  Spark job, not the Flask app).
- The 5-minute idle logout, per-request auth checks, and admin-only config
  routes (`@admin_required`) are the three access-control layers inside the
  app; network-level isolation between `prod_preprod` and `preprod_dev` is a
  cluster-level concern (see DEVOPS_GUIDE §7).
