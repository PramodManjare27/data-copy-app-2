# Data Copy Console — User Guide

This guide covers day-to-day use of both consoles:

- **PROD → PREPROD console** — typically `https://<your-prod-preprod-host>/`
- **PREPROD → DEV console** — typically `https://<your-preprod-dev-host>/`

They look and behave identically except for which target environments are
offered, since they are the same application configured two ways.

## 1. Signing in

1. Open the console URL and enter your username/password.
2. Your session automatically signs out after **5 minutes of inactivity**.
   You'll see a warning banner 30 seconds before this happens — click or type
   anywhere to stay signed in.
3. Every login (and every data copy you trigger) is recorded against your
   username in the audit trail — there is no shared/anonymous access.

*Local demo credentials* (only apply when running this build locally — see
the project README): `admin / Admin@12345` (admin role, can edit configs),
`alice / Alice@12345`, `bob / Bob@123456` (standard users).

## 2. Starting a new data copy request

Click **New Copy Request** from the dashboard. The wizard has up to 4 steps;
a progress tracker across the top always shows where you are.

### Step 1 — Target environment

- On the PROD→PREPROD console this is fixed and skipped automatically.
- On the PREPROD→DEV console, choose one of `DEV`, `DEV_env1`, `DEV_env2`,
  `DEV_env3`, `DEV_env4`. Only tables/locations configured for that specific
  target will appear in the next steps.

### Step 2 — PG2PG (PostgreSQL table copy) — optional

You'll see a card per available table (already filtered to your chosen
target environment). To include a table in this request:

1. Check the box next to it — this expands its detail form.
2. **Target table name** — pre-filled from config. You may change it to copy
   into a different table name. If you do, the system will automatically
   create that table (with the same schema as the source) on the target side,
   and the copy **mode is forced to Append** regardless of what you pick.
3. **Mode** (PREPROD→DEV only) — `Append` adds rows without touching
   existing data; `Reload` deletes matching target rows (per your filter)
   before copying fresh data in.
4. **Custom filter** — an optional SQL-style predicate applied to the
   *source* query, e.g. `created_at >= '2026-01-01' AND status = 'ACTIVE'`.
   This is **not** saved back into the table configuration — it's logged
   against this one request only, so re-running the same table later starts
   from the config defaults again.
5. **Columns table** — every column and its data type is listed. Columns
   flagged `PII` are pre-checked for masking as a safety default; check or
   uncheck any column to control exactly what gets masked.
6. **Masking algorithm** — pick one algorithm (SHA-256 Hash, Partial Mask,
   Full Redact, or Deterministic Tokenization) to apply to every checked
   column for that table. See §5 below for what each one does.

Repeat for as many tables as you need in this one request, then either
**Skip PG2PG** (if you only want ADLS2ADLS) or **Continue**.

### Step 3 — ADLS2ADLS (data lake location copy) — optional

Three tabs group locations by copy category: **In-Place**, **Point-to-Point**,
and **Output**. Each tab's badge shows how many locations are configured for
your chosen target environment.

For each location you check:

- **Target clean-up mode** — `Append` or `Overwrite`, pre-filled from config
  but editable for this run.
- **Partition column / format** — pre-filled from config; used to filter the
  source data by partition (e.g. a date-partitioned lake table). Editable for
  this run only — not saved back to the `.conf` file.
- **Additional filter** — free text, logged in the audit trail, not saved to
  config.
- **Masking columns** — if the location's config lists any, they're shown as
  chips along with the algorithm that will be applied automatically. You
  cannot add masking columns here (they come from config, managed by an
  Admin) — this step is read-only for masking, by design.

You must select at least one PG2PG table or one ADLS2ADLS location across
steps 2–3 (you may skip either step, but not both).

### Step 4 — Review & Submit

A plain-language summary of everything you selected: source/target names,
filters, mode, and exactly which columns will be masked with which
algorithm. Use **Edit PG2PG selection** / **Edit ADLS2ADLS selection** to go
back and change anything. When it looks right, click **Confirm & Submit**.

This immediately:
- Creates one audit log entry per table/location you selected (all linked as
  one request).
- Triggers a Spark job on Databricks for each.
- Takes you to the dashboard, where you'll see them appear under
  **In-progress activity**.

## 3. The dashboard

- **In-progress activity** shows every request currently `QUEUED` or
  `IN_PROGRESS`, each with a live progress bar and its ETA. This section
  auto-refreshes every few seconds while anything is active.
- **Refresh** manually re-pulls the latest status for both sections —
  useful right after submitting, or if you want an up-to-the-second view
  without waiting for the auto-refresh.
- **Audit trail** lists the 50 most recent copy items (one row per
  table/location, not per request) with status, source/target, who
  triggered it, the filter used, masked columns, start time, duration, and
  ETA. Use the **status filter** dropdown to narrow to Queued / In Progress
  / Success / Failed.
- A **Failed** row's underlying error is visible by hovering/expanding the
  error detail (surfaced from `error_description` in the audit record) —
  contact your platform team with the request's timestamp and table name if
  you need to investigate further.

## 4. Admin: editing config files

Users with the **admin** role see an **Admin** menu item leading to a list of
the config files this console instance uses (the PG2PG table definitions and
the three ADLS `.conf` files). Opening one shows a raw JSON editor:

- Edits are validated as JSON before saving — an invalid edit is rejected
  with an error and nothing is written.
- Changes take effect immediately for any *new* copy request started after
  saving; requests already in progress are unaffected.
- Filters and overrides that ordinary users type into the wizard (steps 2–3)
  are never written back here — only an admin editing this screen changes
  what future users see as defaults.

## 5. Masking algorithms reference

| Algorithm | What happens | When to use it |
|---|---|---|
| **SHA-256 Hash** | Irreversible, deterministic hash (same input → same output) | Default choice; lets you still join/group on the masked column without exposing the real value |
| **Partial Mask** | Keeps first/last 2 characters, masks the middle | When a human reviewer needs the data to still *look* plausible |
| **Full Redact** | Replaces the whole value with a fixed placeholder | Strongest option when the column's content doesn't matter at all downstream |
| **Deterministic Tokenization** | Replaces the value with a short reproducible token (`TOK_xxxxxxxx`) | When you need unique-but-anonymous identifiers preserved across the copy |

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Redirected to login unexpectedly | Idle timeout (5 min of inactivity) — just sign in again |
| A table/location doesn't appear in the wizard | It isn't configured for the target environment you picked — ask an Admin to check the relevant config file |
| A request shows **Failed** | Check `error_description` on the audit row; common causes are logged there (e.g. a JDBC timeout). Re-submit the same request once the underlying issue is resolved |
| Renamed a target table but mode still shows Append | Expected — renaming always forces Append plus new-table creation, by design |
