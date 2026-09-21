# Release & Rollback Procedure

This document describes the actual release model for the
**Agentic AI-Based Sentiment Analysis Management System**. It is
honest about what is safe and what is risky.

The recommended deployment is the **Docker Compose** stack under
`docker-compose.yml`. Note: the compose topology has been statically
validated but **not runtime-executed** on the certification host (no
Docker daemon there); the runtime-verified path is the on-host
deployment (waitress/gunicorn + PostgreSQL [+ Redis for multi-instance]).
The architecture separates the database
migration step from application startup so a failed migration never
leaks into a half-migrated fleet.

---

## 1. Release flow (per deployment)

```text
1. Capture pre-deployment state
   - PostgreSQL: pg_dump into a timestamped file
   - reports_data volume: snapshot or just note its size
   - record current image tags (git SHA)

2. Apply database migration as a one-shot job
   docker compose up migrate
   This runs ``flask db upgrade head`` against the live database
   and exits 0. If it exits non-zero, STOP — do not roll out
   application containers.

3. Bring up the new application version
   docker compose up -d backend
   docker compose up -d frontend

4. Smoke-verify
   curl -fsS https://app.example.com/api/v1/health
   curl -fsS https://app.example.com/api/v1/ready
   Authenticate and exercise one full workflow.

5. If healthy, route traffic (the proxy already does this if
   health checks pass).

6. If unhealthy, see section 3.
```

Migration 0009 is the current head. Migrations 0001–0009 are
**forward-only** in the production chain. `flask db downgrade` is
reversible for individual revisions but is not a routine operation:
some migrations are not fully reversible (e.g. dropping a column
without keeping its data). Always treat a migration as
**forward-only** in production.

---

## 2. Compatibility

The application is designed so that the application code can be
rolled back to any previous tag without database changes **as long as
the database is at the same or later migration head as the code
expects**.

If a previous release tag was at migration `0008` and the database
is at `0009`, **rolling back to that tag is unsafe** — the application
may attempt to read or write columns that 0009 introduced but 0008
does not know about.

Therefore: **never roll the application back to a tag older than the
database migration head it was originally paired with**.

---

## 3. Rollback (when the new release is broken in production)

### Step 1: Stop the broken application

```bash
docker compose stop backend frontend
```

### Step 2: Restore the previous image tags

Edit `docker-compose.yml` to set the image references to the known-good
git tag, or use the compose override file convention.

### Step 3: Bring the previous version back up

```bash
docker compose up -d backend frontend
```

### Step 4: If the previous version requires an older migration

This is the dangerous case. The previous tag may not understand the
current migration head. Two options:

#### Option A (preferred): forward-fix the new release

Re-enable the new release, fix the bug, redeploy. This avoids any
database mutation.

#### Option B: database downgrade

```bash
docker compose run --rm migrate flask db downgrade -1
```

Only do this if the migration you are downgrading from is **fully
reversible** (no destructive operations). Migrations authored in this
repository use SQLAlchemy `op.alter_column`/`op.add_column` style
changes and are reversible for additive cases. Migrations that drop
data or columns are not reversible.

If the broken release included a destructive migration, restore from
the pre-deployment `pg_dump` instead:

```bash
# Stop all writers
docker compose stop backend frontend migrate

# Restore
gunzip -c pre-deploy-YYYYMMDDTHHMMSSZ.sql.gz \
  | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# Restart on the previous application tag
docker compose up -d
```

---

## 4. What is explicitly NOT safe

- `docker compose down -v` — **destroys the `db_data` and
  `reports_data` volumes**. Never run this in production.
- Editing a migration file after it has been applied — Alembic
  detects checksum drift and refuses further upgrades.
- Downgrading the database after a destructive migration —
  the data is gone.

---

## 5. Pre-deployment checklist

```text
[ ] git status is clean (or committed)
[ ] migration audit passes locally
[ ] pytest passes
[ ] npm run build passes
[ ] PostgreSQL backup was taken
[ ] migration has been rehearsed against staging
[ ] image tag for the new release is recorded
[ ] image tag for the previous (known-good) release is recorded
[ ] rollback plan reviewed (this document)
```

The migration audit at `backend/scripts/audit_migration_postgres.py`
runs the full 0001→0009 chain against an isolated schema and
verifies downgrade→re-upgrade. It is the recommended pre-deploy
gate.

---

## 6. What this document deliberately does NOT promise

- **Hot code reload**. The production stack uses gunicorn's
  pre-fork model; there is no in-place reload. Redeploys are
  full restart.
- **Blue/green / canary**. Not implemented. A single compose stack
  is the documented deployment; running two in parallel would
  require a separate design.
- **Database migration without app restart.** Not implemented.
  Migrations are applied before the application starts; the
  `migrate` service in compose runs once per `up` and exits.