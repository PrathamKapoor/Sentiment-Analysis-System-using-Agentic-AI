# Production Deployment Guide

This document describes how to deploy the **Agentic AI-Based Sentiment
Analysis Management System** to a production environment.

It covers the architecture, environment variables, database setup,
migrations, application server, observability, security defaults,
backup / recovery, and a smoke-test workflow that must pass before a
deployment is considered live.

The expected production operating system is **Linux** (Debian-family).
A **Windows** host is supported only for development and the smoke
test below; the canonical production image runs on Linux.

---

## 1. Architecture

```text
Internet
   │
   ▼
TLS termination (load balancer / CDN / nginx)
   │
   ▼
nginx reverse proxy (frontend container)
   │
   ├── /          → static React build (nginx → html)
   │
   └── /api/v1/   → backend service (gunicorn → Flask)
                          │
                          ▼
                       PostgreSQL
```

Components:

- **Frontend container** — `nginx:1.27-alpine` serving the React
  production build. It reverse-proxies `/api/v1/*` to the backend
  service on the same Docker network. Static assets (JS, CSS, fonts)
  are cached for one year with `immutable`; the HTML entry is
  revalidated by the browser.
- **Backend container** — `python:3.13-slim` running `gunicorn`
  with 2 workers × 2 threads and a 120-second request timeout.
  `gunicorn` is the Linux production WSGI server. On a Windows host
  the same app runs under `waitress` (entrypoint
  `python -m app.runner`).
- **PostgreSQL container** — `postgres:18-alpine` with a named
  volume (`db_data`) for persistent storage. Migrations are applied
  by the backend container on startup **before** `gunicorn` starts.

Celery is deliberately **not** introduced. All current
report / LLM / collection / analysis operations are short enough to
be served inline within the gunicorn worker. The application was
designed for synchronous execution; an asynchronous job system is
deferred until a measured need exists.

Redis is **not an application dependency** — the app runs correctly
with zero Redis. It is only the recommended *shared state backend*
when you scale past one replica: `LIMITER_STORAGE_URL` (rate-limit
budgets) and `REVOCATION_STORE_URL` (JWT logout/refresh revocation).
Single-instance deployments leave both unset. See the "Recommended"
env table for the horizontal-scaling contract.

---

## 2. Prerequisites

| Requirement   | Version  | Notes                                |
| ------------ | -------- | ------------------------------------ |
| Docker       | ≥ 24.0   | for `docker compose up --build`      |
| Docker Compose | v2 (bundled) |                                |
| PostgreSQL   | 18       | or 14+                                |
| TLS certs    | real     | owned at the proxy layer, not in app |

---

## 3. Environment variables

All sensitive values come from environment variables. The file
`backend/.env.example` documents every key with safe placeholder
values. The full set the backend reads:

### Required

| Variable          | Purpose                                                 |
| ----------------- | ------------------------------------------------------- |
| `FLASK_ENV`       | `production` for the deployed stack                     |
| `SECRET_KEY`      | Flask session/CSRF secret (≥ 32 random bytes)           |
| `JWT_SECRET_KEY`  | JWT signing key (≥ 32 random bytes, distinct)           |
| `DATABASE_URL`    | SQLAlchemy URL, e.g. `postgresql+psycopg://USER:PASS@db:5432/DB` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact origins, e.g. `https://app.example.com` |

The application **fails fast** in production if any of the above is
missing or matches the development default
(`change-me`/`dev-`). See `ProductionConfig.validate_environment`.

### Recommended

| Variable               | Default            | Purpose                              |
| ---------------------- | ------------------ | ------------------------------------ |
| `TRUSTED_PROXY_COUNT`  | `0`                | Set to `1` behind nginx/ALB          |
| `LOG_JSON`             | `true`             | One JSON object per log line          |
| `LOG_LEVEL`            | `INFO`             | Or `WARNING` in quiet environments   |
| `RATE_LIMIT_ENABLED`   | `true`             | Per-route limits on auth / cost paths |
| `LIMITER_STORAGE_URL`  | `memory://`        | `redis://...` for multi-worker/multi-instance — **required for horizontal scaling** (per-process otherwise) |
| `REVOCATION_STORE_URL` | unset (in-memory)  | `redis://...` for multi-instance JWT logout/refresh revocation — **required for horizontal scaling** |
| `REVOCATION_STORE_PREFIX` | `sams:revoked:` | Redis key namespace for revocations |
| `WEB_CONCURRENCY`      | `4` (waitress)     | Threads for waitress host            |
| `UPLOAD_FOLDER`        | unset (instance/)  | Backing dir for uploaded datasets    |
| `REPORT_OUTPUT_DIRECTORY` | unset (instance/)| Backing dir for generated reports    |

> **Horizontal scaling contract.** With more than one replica you MUST
> set both `LIMITER_STORAGE_URL` and `REVOCATION_STORE_URL` to a shared
> Redis. Without them, each replica keeps its own rate-limit budget
> and its own revoked-token list, which silently multiplies attacker
> budgets and lets logged-out tokens live on other replicas. The
> `redis` Python package ships in `requirements.txt`; the Redis-backed
> behavior is runtime-verified against a real Redis server by
> `backend/scripts/phase14_distributed_verification.py` (two live
> processes + real HTTP, including restart persistence). If a
> Redis-backed revocation store is configured but unreachable, reads
> fail closed (tokens are treated as revoked) and writes fail loudly.

The canonical per-variable matrix — required/optional, dev default,
production behavior, security impact — is
`docs/production_configuration_matrix.md`.

### Optional

| Variable                    | Default       | Purpose                                  |
| --------------------------- | ------------- | ---------------------------------------- |
| `DB_POOL_SIZE`              | `5`           | SQLAlchemy pool size                     |
| `DB_POOL_MAX_OVERFLOW`      | `5`           | SQLAlchemy overflow                      |
| `DB_POOL_RECYCLE_SECONDS`   | `1800`        | Recycle interval to avoid stale conns     |
| `LLM_PROVIDER`              | `deterministic` | `openai_compatible` to enable real LLM  |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | unset | Required only when `LLM_PROVIDER=openai_compatible` |
| `LLM_TIMEOUT_SECONDS`       | `20`          | Per-request timeout                      |
| `LLM_MAX_TOKENS`            | `512`         | Per-request cap                          |
| `SCRAPER_*`                 | see `.env.example` | Network collection tuning           |
| `SENTIMENT_ENGINE`          | `vader`       | Pluggable sentiment engine              |

### Frontend

| Variable                | Default            | Purpose                          |
| ----------------------- | ------------------ | -------------------------------- |
| `VITE_API_BASE_URL`     | `/api/v1`          | Built into `dist/assets/*.js`    |

The frontend build embeds `VITE_API_BASE_URL` at `npm run build`
time. In the bundled docker image the default `/api/v1` works
because nginx proxies `/api/` to the backend. For external hosting,
set the absolute URL (e.g. `https://api.example.com/api/v1`).

---

## 4. First-time setup

```bash
# 1. Copy and edit secrets
cp backend/.env.example backend/.env
$EDITOR backend/.env
# - set SECRET_KEY, JWT_SECRET_KEY to strong random values
# - set DATABASE_URL to the production PostgreSQL
# - set CORS_ALLOWED_ORIGINS to the public frontend URL

# 2. Set the compose-time DB credentials
cat > .env <<'EOF'
POSTGRES_USER=sentiment_app_user
POSTGRES_PASSWORD=$(openssl rand -hex 32)
POSTGRES_DB=sentiment_agentic_prod
SECRET_KEY=<same as backend/.env>
JWT_SECRET_KEY=<same as backend/.env>
EOF
chmod 600 .env

# 3. Build and start the stack
docker compose up --build -d

# 4. Wait for the backend to finish migrations + seed, then verify
docker compose ps
docker compose logs backend --tail=200
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -fsS http://127.0.0.1:8080/api/v1/ready
```

The backend container's command runs `flask db upgrade && flask seed`
before starting gunicorn, so migrations are always current before any
HTTP traffic is served.

---

## 5. Migrations

```bash
# Apply pending migrations
docker compose exec backend flask db upgrade

# Inspect current head
docker compose exec backend flask db current

# Roll back one revision
docker compose exec backend flask db downgrade -1
```

Migrations live under `backend/migrations/versions/`. Do not delete
or renumber accepted migrations. The PostgreSQL chain is
`0001 → 0009`; SQLite shares the same chain.

Migration rollout rules:

1. Take a PostgreSQL backup before running `flask db upgrade`.
2. Apply the migration on a staging clone first.
3. Verify the migration on staging: row counts, JSON/UUID columns,
   foreign-key integrity.
4. Only then apply on production.
5. If the migration fails, restore the backup and
   `flask db downgrade` to the previous head.

The script `backend/scripts/audit_migration_postgres.py` exercises
the full chain on a disposable schema and is runnable in CI to
guard against portability regressions.

---

## 6. Backup and recovery

The deployment's only persistent state is PostgreSQL. Backups are
mandatory; the application does not manage them itself.

### Backup

```bash
# Logical, portable backup
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "backup-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
```

Schedule via cron / systemd timer; keep at least 7 daily, 4 weekly,
and 3 monthly copies. Verify backups by restoring into a disposable
container or schema periodically.

**Verified drill.** `backend/scripts/phase14_pg_dump_drill.py`
performs a real operator-tool drill with the installed `pg_dump` /
`pg_restore` 18.6 binaries against an isolated `p14_drill_src` schema
inside the configured development database: full Alembic migration
into the schema, FK-ordered data population, custom-format dump,
`DROP SCHEMA CASCADE`, plain restore, snapshot comparison, then a
corruption pass restored with `pg_restore --clean --if-exists`.
Snapshot equality covers row counts, per-table md5 over ordered
`row_to_json` output (UUID/JSONB/timestamps included), FK and index
counts, and the `alembic_version` head. Run it after provisioning a
new database host or PostgreSQL upgrade. The older
`scripts/phase13_backup_drill.py` remains as a psycopg-level drill for
environments where the operator binaries are absent; the two are not
equivalent.

Generated reports and uploaded datasets are stored under
`/data/reports` and `/data/uploads` inside the backend container.
For multi-instance deployments they must be moved to object storage
(S3 / GCS); the `storage_service` abstraction is already in place
to accept a future object-storage adapter.

### Restore

```bash
# Stop the application
docker compose stop backend

# Recreate the database from a logical backup
gunzip -c backup.sql.gz | docker compose exec -T db psql \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# Restart the application
docker compose start backend
```

Point-in-time recovery is possible only if you run PostgreSQL with
WAL archiving enabled at the host layer. The bundled compose
configuration does not enable WAL archiving; for production a
managed PostgreSQL or `wal-g`/`pgbackrest` is recommended.

---

## 7. Application server

### Production (Linux)

```text
gunicorn -b 0.0.0.0:5000 --workers 2 --threads 2 --timeout 120 run:app
```

Tuning:

- **Workers**: `2 * CPU + 1` is the textbook formula; the bundled
  value of `2` keeps memory small for a small-team deployment.
- **Threads**: `2` per worker — Flask-SQLAlchemy releases the GIL
  during I/O so two threads per worker give useful concurrency
  without ballooning DB pool pressure.
- **Timeout**: `120s` to accommodate large dataset uploads, PDF
  generation, and slower LLM calls.

### Development / Windows

```powershell
cd backend
python -m app.runner
```

`app/runner.py` boots waitress with `WEB_CONCURRENCY` threads on
`BIND_ADDRESS:PORT`. It is **not** used in production.

### Forbidden

- `flask run` — debug-mode, single-threaded.
- `python run.py` — development entrypoint, calls `app.run`.

---

## 8. Observability

### Logs

- Every log line is a single JSON object.
- Each request carries an `X-Request-ID` header (incoming or
  auto-generated). The id is echoed in the response and attached
  to every log line.
- Sensitive fields are never logged by the application.

Sample:

```json
{"timestamp":"2026-09-05T16:08:00+00:00","level":"INFO","logger":"app.limiter","message":"rate limiting enabled (storage=memory://)","requestId":"smoke-test-001"}
```

### Health endpoints

| Endpoint             | Status | What it checks                                    |
| -------------------- | ------ | ------------------------------------------------- |
| `GET /api/v1/health` | 200    | Process is alive.                                 |
| `GET /api/v1/live`   | 200    | Alias for `/health` (Kubernetes-style).           |
| `GET /api/v1/ready`  | 200/503 | 200 if DB reachable; 503 otherwise.            |

The optional LLM provider is **not** part of readiness. A missing
LLM does not make the deterministic pipeline unavailable.

### Request tracing

```bash
curl -H 'X-Request-ID: my-trace-id' \
     https://app.example.com/api/v1/health
# response header X-Request-Id: my-trace-id
```

---

## 9. Security defaults

### Already enforced

- `DEBUG = False`, `TESTING = False` in production.
- Required secrets validated at app startup; the dev defaults are
  rejected with a clear error.
- CORS restricted to the configured `CORS_ALLOWED_ORIGINS` (exact
  origins, no `*`); credentials allowed only for those origins.
- `ProxyFix` honors `X-Forwarded-*` headers only when
  `TRUSTED_PROXY_COUNT > 0`. Set it to the number of trusted
  proxies in front of the app. If the app is exposed directly to
  the internet, leave it at `0`.
- SSRF protections from Phase 10 are intact: localhost, RFC1918,
  link-local, and unsafe redirects remain blocked.
- File uploads are size-limited (default 25 MiB), extension- and
  content-validated, and path-traversal-protected.
- Login / register / report generation / website-context refresh
  are rate-limited (10/min for login/register, 10/min for reports,
  10/min for website refresh). Health endpoints are exempt.

### HTTPS

TLS is terminated at the reverse proxy / load balancer. The
application does not manage certificates. Production deployments
must put the app behind a proxy that owns the cert.

### CORS

```text
CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
```

Wildcards are not supported by intent. If you operate a single
domain, list that one origin.

### Rate limiting

- Default memory store works for a single process.
- For multiple workers/replicas, set `LIMITER_STORAGE_URL=redis://...`.
  A shared budget across two live processes was runtime-verified on
  2026-09-06 (10/min login budget: 5 accepted on process C + 5 on
  process B, 11th and 12th rejected 429 on both — see
  `scripts/phase14_distributed_verification.py`).
- Health endpoints are exempt — see `app/limiter.py`.

### Token revocation

- Logout and refresh rotation revoke the token's `jti` in the active
  revocation store.
- Single process: in-memory store (default, dev/test safe).
- Multi-instance: `REVOCATION_STORE_URL=redis://...`. Verified
  behaviors: revocation on instance A rejects the token on instance B;
  old refresh tokens are rejected on both instances after rotation;
  revocations survive a full fleet restart (Redis persistence); Redis
  keys expire automatically with the token's remaining lifetime;
  read outages fail closed (treat as revoked), write outages raise.
- Unknown `REVOCATION_STORE_URL` schemes refuse to boot.

---

## 10. Frontend production configuration

The frontend is a static SPA. The build is produced by:

```bash
cd frontend
VITE_API_BASE_URL=/api/v1 npm run build
```

In the bundled image, nginx reverse-proxies `/api/` to the backend
container. The API base URL is therefore the path-only default
(`/api/v1`). For external API hosting, set
`VITE_API_BASE_URL=https://api.example.com/api/v1` at build time.

---

## 11. Smoke test

A minimal smoke test should be run after every deploy:

```bash
# 1. Health endpoints
curl -fsS http://127.0.0.1:8080/api/v1/health   # 200
curl -fsS http://127.0.0.1:8080/api/v1/live     # 200
curl -fsS http://127.0.0.1:8080/api/v1/ready    # 200

# 2. Frontend index loads
curl -fsS http://127.0.0.1:8080/ | head         # 200, <html>

# 3. Request-ID propagates
curl -fsS -H 'X-Request-ID: smoke' \
  http://127.0.0.1:8080/api/v1/health \
  -i | grep X-Request-Id                        # smoke

# 4. CORS preflight from the configured origin succeeds
curl -fsS -X OPTIONS \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  http://127.0.0.1:8080/api/v1/auth/login -i
```

The script `backend/scripts/smoke_concurrency.py` runs a burst
of 200 health requests at concurrency 10 against the local backend
and reports throughput / latency. It is safe to run in CI or after
a deploy.

---

## 12. Update / rollback

Updates:

```bash
git pull
docker compose build
docker compose up -d
docker compose logs backend --tail=200
```

Rollback:

```bash
# Code rollback
git checkout <previous-tag>
docker compose build
docker compose up -d

# Database rollback
docker compose exec backend flask db downgrade -1
```

---

## 13. Common failure modes

| Symptom                                 | Likely cause                              |
| --------------------------------------- | ----------------------------------------- |
| 503 from `/api/v1/ready`                | PostgreSQL unreachable or credentials wrong|
| 429 on `/api/v1/auth/login`             | Rate limit; back off                      |
| 401 on every API call                   | Missing/rotated `JWT_SECRET_KEY`          |
| 401 on all requests right after Redis outage | Revocation store fail-closed; restore Redis |
| `RuntimeError ... REVOCATION_STORE_URL ... not a supported scheme` | bad scheme; use `redis://`/`rediss://` or unset |
| Migration fails on `flask db upgrade`   | Out-of-date schema; restore backup, retry |
| `RuntimeError: Missing required production env` | `.env` not loaded                  |

---

## 14. Versioning

Production images are tagged with the git commit SHA
(e.g. `ghcr.io/acme/sams-backend:ddd4bff`). Tags are immutable;
rolls forward or back by changing the image tag.