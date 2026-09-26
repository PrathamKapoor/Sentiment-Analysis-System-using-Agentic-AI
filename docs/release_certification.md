# Release Certification — Agentic AI-Based Sentiment Analysis Management System

This is the formal release certification for the system. Each row
is evidence-based. Where a verification is not possible in this
environment, the row is honestly classified.

The verification environment is **Windows 11, Python 3.13.14,
Node 24.19.0, PostgreSQL 18.6 on localhost:5432, Redis 5.0.14.1 on
localhost:6379 (Windows service), pg_dump/pg_restore/psql 18.6**.
Docker and Trivy are **NOT available** in this environment; those rows
are classified as `ENVIRONMENT BLOCKED` / `NOT RUN — TOOL UNAVAILABLE`.

**Phase 14 rows** are marked **(P14)**. Phase 14 was executed in two
stages: an implementation stage (revocation-store abstraction, limiter
wiring tests, env/config matrix) and a **runtime-verification stage**
performed on 2026-09-06 after Redis and the PostgreSQL client binaries
were found available on this workstation. The second stage upgraded
several rows from `IMPLEMENTATED NOT VERIFIED` / `ENVIRONMENT BLOCKED`
to `VERIFIED` with real-process, real-Redis, real-`pg_dump` evidence.

---

## Certification Matrix

| Area | Status | Evidence | Limitation |
| --- | --- | --- | --- |
| Repository integrity | VERIFIED | `git status` preserved; HEAD `5db31fa`; no destructive git operations executed; `backend/.env` is gitignored. | None. |
| Backend regression suite | VERIFIED | `python -m pytest -q` → **414 passed, 0 failed, 2 warnings** (includes 5 new real-Redis integration tests, 10 revocation + 4 limiter-wiring unit tests, and 13 CORS-allowlist tests added with the Flask-CORS 5.x → 6.x security upgrade). | None. |
| Dependency audit | VERIFIED (clean) | `pip-audit -r requirements.txt` → **No known vulnerabilities found** (exit 0). Previously 16 advisories across 5 packages; resolved by Flask 3.1.3, Flask-CORS 6.0.5, marshmallow 3.26.2, python-dotenv 1.2.3, pytest 9.1.1. `npm audit` → **0 vulnerabilities** (prod and dev) after `react-router-dom` 6.28.0 → 7.18.4 and a `nanoid` dev-tree bump. | The CI `security-scans` job stays `continue-on-error: true` by policy, so a future advisory is reported but does not block unrelated pushes. |
| Frontend routing (React Router 7) | VERIFIED (real browser) | Headless Chromium against the production build + a live Flask backend: real registration and login, then all 18 authenticated routes, the nested project workspace (`Outlet` + `useOutletContext` + `useParams`), `NavLink` resolution and client-side `Link` navigation without a page reload. 0 console errors, 0 uncaught page errors. | Routing only. The rendered *content* of every page under live data is not yet walked. |
| Frontend production build | VERIFIED | `npm run build` exits 0; `dist/index.html` + hashed JS/CSS emitted (7.17s). | Bundle-size warning (>500 kB chunk) is informational. |
| PostgreSQL migrations | VERIFIED | `python -m scripts.audit_migration_postgres` → upgrade→downgrade→re-upgrade clean in isolated schema; ≥25 tables; JSON + UUID verified. | None. |
| PostgreSQL runtime | VERIFIED | Real PostgreSQL 18.6; psycopg v3; pooled with `pre_ping` + recycle. | Localhost server, not the alpine container. |
| Full end-to-end workflow | VERIFIED | Phase 12 smoke: register → project → upload → process → sentiment/topics/aspects → PDF (`%PDF`) + Excel (`PK`) reports. | None. |
| **JWT revocation (multi-instance)** | **VERIFIED (P14)** | `TokenRevocationStore` Protocol + `InMemoryRevocationStore` + `RedisRevocationStore`; **runtime proof with two real waitress processes + real Redis** via `scripts/phase14_distributed_verification.py`: token minted on A accepted on B (200); logout on A → same token rejected on B (401); refresh rotated on B → old refresh rejected on BOTH (401); revocation survives killing the entire fleet and booting a fresh process C (401). 5 real-Redis integration tests prove cross-instance visibility, key namespacing, TTL ≤ remaining token lifetime, automatic expiry after the token's life, and fresh-client visibility. | Redis-backed store is configured by `REVOCATION_STORE_URL`; without it the store is per-process (documented). |
| **Distributed rate limiting** | **VERIFIED (P14)** | Two live processes sharing `LIMITER_STORAGE_URL=redis://…/6`: 5 accepted logins on C + 5 on B exhaust the shared 10/min budget; request 11 on C → 429, request 12 on B → 429. In-process two-limiter integration test against real Redis passes. Scripts flush only Redis logical DBs 5/6/13/14. | Window arithmetic is server-time based; sub-second boundary races are inherent to any windowed limiter and are handled by the script's quiet-period design. |
| Rate limiting (single-process) | VERIFIED | 15-burst login → 429 after 10/min; health burst → all 200. | None. |
| **Token revocation store — fail safety** | **VERIFIED (P14)** | Unit tests: Redis read outage → `is_revoked` returns True (fail-closed); write outage raises (logout fails loudly rather than silently not revoking); unknown `REVOCATION_STORE_URL` scheme refuses to boot; missing `redis` package raises at store construction, not at first request. | None. |
| **Operator backup tool (pg_dump)** | **VERIFIED (P14)** | `scripts/phase14_pg_dump_drill.py` with real `pg_dump`/`pg_restore` 18.6: isolated schema `p14_drill_src` fully migrated (0001→head, 26 relations), 25 tables populated FK-ordered from dev data (20 nonempty, ~1,348 rows incl. JSONB/UUID/unicode), 147,247-byte custom-format dump, `DROP SCHEMA CASCADE`, plain `pg_restore` → **exact snapshot match** (row counts + md5 over ordered `row_to_json`), FK count 39, indexes 73, `alembic_version` = `0009`; then corruption injected (rows deleted + table dropped) → `pg_restore --clean --if-exists` → **exact snapshot match again**. | Drill ran against the dev database's isolated schema, not a production-volume dataset; policy is that this does not claim production-scale timing. |
| Restore drill (Python-level) | VERIFIED | Phase 13 `phase13_backup_drill.py`: psycopg pickle round-trip of 8 representative tables. Retained as the fallback drill where operator binaries are absent. | **Not equivalent** to pg_dump; kept honestly separate. |
| Docker image build | STATICALLY VALIDATED | Multi-stage `backend/Dockerfile` (python:3.13-slim, non-root `appuser`, libpq5 runtime-only, `pip --no-cache-dir`, HEALTHCHECK, gunicorn CMD); `frontend/Dockerfile` (node:24 build → nginx:1.27-alpine). `.dockerignore` excludes `.env`, `tests/`, `fixtures/`, `scripts/` (P14: added missing `tests/` exclusion). | No `docker build` executed here. |
| Docker Compose runtime | ENVIRONMENT BLOCKED | `docker --version` → command not found. Compose YAML parsed successfully (4 services: db/migrate/backend/frontend; migrate is a one-shot job; backend `depends_on: service_completed_successfully`). Compose now passes `REVOCATION_STORE_URL` through to the backend (P14). | Docker daemon unavailable in this environment. |
| nginx runtime | IMPLEMENTED NOT VERIFIED | `frontend/nginx.conf` proxies `/api/`; production image is `nginx:1.27-alpine`. | No container runtime. |
| Gunicorn runtime | IMPLEMENTED NOT VERIFIED | Dockerfile CMD `gunicorn -b 0.0.0.0:5000 --workers 2 --threads 2 --timeout 120`. | Not exercised here; waitress (same app object) is runtime-verified on Windows. |
| Health/readiness/liveness | VERIFIED | `/health` 200, `/live` 200, `/ready` 200 with DB up / 503 with DB down (controlled test). | None. |
| Structured logging | VERIFIED | JSON one-line logs with `timestamp/level/logger/message/requestId` captured from a live server. | None. |
| Request correlation | VERIFIED | `X-Request-ID` echoed in response headers and attached to every log line. | None. |
| Authentication/JWT | VERIFIED | Real register/login round-trips; blocklist callback delegates to the active `TokenRevocationStore`. | None. |
| SSRF protection | VERIFIED | `tests/test_website_security.py` passes; localhost/RFC1918/redirect revalidation enforced. `SCRAPER_ALLOW_PRIVATE_TARGETS` is env-only and defaults false. | None. |
| Prompt-injection protection | VERIFIED | `tests/test_prompt_injection.py` passes; untrusted text never becomes agent authority. | None. |
| Upload security | VERIFIED | 25 MiB cap, extension+content validation, path-traversal blocked. | None. |
| LLM failure isolation | VERIFIED | Deterministic provider always available; `/llm/status` reports provider state; analysis works with no LLM. | No real paid LLM endpoint exercised here (by design). |
| Persistence | VERIFIED | Server stop/start preserves data (PostgreSQL). | None. |
| Concurrency/load | VERIFIED | Phase 12/13 localhost load runs (see prior phase records). | Localhost only; not an internet-scale claim. |
| **Multi-instance readiness** | **VERIFIED for security state (P14)** | Two processes + shared Postgres + shared Redis: JWT accept/revoke/rotate and rate-limit budget all behave as ONE system across processes and across a full fleet restart. | Uploads/reports still need a shared volume or `STORAGE_BACKEND=s3` for multi-instance file availability; collection lock is process-local by design (see matrix below). |
| Object storage (S3) | TESTED WITH MOCKS | `S3StorageBackend` interface implemented; 5 unit tests with a fake boto3 module. | No real S3/MinIO here; boto3 not installed. |
| TLS edge deployment | DOCUMENTED | `docs/nginx_production.conf` with HTTPS redirect, HSTS, proxy headers. | Needs a real domain + certificate. |
| Container security scan | NOT RUN — TOOL UNAVAILABLE | `trivy` not installed. Command documented: `trivy image --severity HIGH,CRITICAL <image>`. | Static Dockerfile inspection only. |
| **Production configuration matrix** | **VERIFIED (P14)** | `docs/production_configuration_matrix.md` created — every backend env var classified (required?, dev default, production behavior, security impact); `.env.example`, compose, and deployment guide aligned. | Human consistency, not mechanically enforced. |
| CI | STATICALLY VALIDATED | `.github/workflows/ci.yml` runs backend tests + frontend build. | Not executed on a GitHub runner here. |
| Rollback | DOCUMENTED | `docs/release_rollback.md` operator procedure; pre-release backup mandatory. | No live rollback performed here. |

---

## Multi-instance statefulness matrix (P14, runtime-backed)

| Component | Stateless? | Shared backend required? | Multi-instance safe? | Evidence |
| --- | --- | --- | --- | --- |
| JWT access tokens | YES (signed) | No | **SAFE** | Token minted on A accepted on B (HTTP 200) |
| JWT refresh tokens | YES (signed) | No | **SAFE** | Refresh issued by A accepted on B |
| Token revocation | NO | **Redis** | **SAFE when configured** (VERIFIED) | Revoked on A → rejected on B (401); survives full fleet restart; TTL-bounded keys |
| Rate limiting | NO | **Redis** | **SAFE when configured** (VERIFIED) | 5+5 accepted across processes, 11th/12th → 429 on both |
| PostgreSQL | NO | Yes (the database) | **SAFE** | Pooled, `pre_ping`, recycle; both processes share it in the P14 drill |
| Uploads (datasets) | NO (files) | Shared volume / object storage | **REQUIRES SHARED BACKEND** | Local disk by default; `STORAGE_BACKEND=s3` implemented, mock-tested only |
| Generated reports | NO (files) | Shared volume / object storage | **REQUIRES SHARED BACKEND** | Same as uploads |
| Background work | YES (none) | n/a | **SAFE** | No in-process queues; synchronous design |
| Flask sessions | n/a | n/a | **SAFE** | `flask.session` unused (grep-verified) |
| Caches | YES (analyzers/providers) | No | **SAFE** | Only immutable singletons (VADER analyzers, LLM provider handle, storage handle); no `@lru_cache` anywhere in `app/` |
| Request IDs | YES | No | **SAFE** | Per-request `g`-scoped |
| Seed operations | YES | n/a | **SAFE** | Idempotent; safe on every replica |
| LLM configuration | YES | n/a | **SAFE** | Env-only; deterministic fallback always available |
| Collection lock | NO (process-local) | (by design) | **PROCESS-LOCAL BY DESIGN** | `threading.Lock` serializes collection per process; two replicas could collect concurrently — documented limitation; distributed collection lock is deferred redesign |
| Revocation store module cache | NO | (per-process handle) | **SAFE** | Module-level `_store` is the *client*, not the state; state lives in Redis |

---

## Status legend

- **VERIFIED** — actually executed and observed in this environment.
- **STATICALLY VALIDATED** — configuration/code parsed and inspected; not executed.
- **IMPLEMENTED NOT VERIFIED** — code/config exists but the environment cannot exercise it.
- **TESTED WITH MOCKS** — exercised against a controlled fake, not the real external service.
- **DOCUMENTED** — operator-facing instructions; the document is the contract.
- **ENVIRONMENT BLOCKED** — required infrastructure is not available in this workstation.
- **NOT RUN — TOOL UNAVAILABLE** — verification tool absent; command documented for operators.

---

## Production gaps that remain

1. **Docker runtime** — compose/Dockerfiles statically valid; no Docker daemon here to execute them. **ENVIRONMENT BLOCKED.**
2. **Trivy image scan** — tool not installed. NOT RUN; command documented.
3. **Real S3/MinIO** — backend implemented, unit-tested with mocks only.
4. **TLS** — documented; needs a real domain/certificate.
5. **Shared file storage for multi-instance uploads/reports** — architectural requirement documented; S3 backend mock-tested.
6. **Distributed collection lock** — collection is serialized per-process by design; multi-worker collection concurrency is a documented deferred redesign (P2).
7. **Idempotency TTL** — pre-existing documented P3 debt.

---

## Honest summary

The application is **production-deployable and runtime-verified as a
single-instance PostgreSQL-backed deployment**, and — new in this
phase — its **multi-instance security state is now runtime-verified**:
JWT revocation and rate limiting were proven across two real OS
processes backed by one real Redis server, including logout
propagation, refresh-token rotation replay rejection, full-fleet
restart persistence, and a shared 10/min login budget enforced
identically on both replicas.

The operator backup path is now verified with the **real `pg_dump` /
`pg_restore` 18.6 binaries** against a fully migrated, populated
schema, including a destroy-and-restore cycle and a
`--clean --if-exists` restore over corrupted data, with byte-exact
row-level snapshots, 39 FKs, 73 indexes, and the `0009` migration head
all preserved.

Still **not** verified in this environment: the Docker/compose/gunicorn
runtime (no daemon), Trivy scanning (no tool), real S3 (mocks only),
and TLS termination (needs a real domain). Those remain honestly
classified above. The system continues to make no claim of autonomous
LLM reasoning: the pipeline is deterministic, the LLM layer is
optional, and LLM failure never blocks analysis or reporting.

---

# Phase 15 / 15.1 — Freeze Consistency Addendum (normative)

This addendum exists so the certification survives adversarial review.
It supersedes any looser phrasing elsewhere in this document.

## 1. Git working tree vs. hygiene (do not conflate)

The Git **working tree is not clean** as of this certification: the
accumulated Phase 8–15 release work (91 pre-existing modified/untracked
paths plus the Phase 14/15 changes listed below) is intentionally
**uncommitted** per the operator's no-commit instruction. This is a
*change-management state*, not a hygiene defect.

Separately, the repository **hygiene** state is verified: no tracked
`.env`, key, or credential files; database credentials removed from all
script files (read from the gitignored `backend/.env`); a zero-byte
phantom artifact (`nul`, accidental shell redirect) deleted;
verification-run leftovers (logs, dumps, drill schemas, Redis logical
DBs 5/6/13/14) confirmed cleaned. "Clean" in this certification means
*hygiene-clean only*.

**BLOCKERS FOR THE INTENDED ON-HOST SINGLE-INSTANCE DEPLOYMENT: none.**
The Docker/compose/gunicorn topology is a *recommended* deployment
variant that is statically validated but not runtime-verified on the
certification host; it is not a blocker for the verified deployment
scope, and this certification does not claim otherwise.

## 2. Historical vs. canonical documentation

No known stale claims remain in **canonical current-state
documentation** (this file, `README.md` quick-answers/setup sections,
`docs/production_deployment.md`,
`docs/production_configuration_matrix.md`, `AGENTS.md` current-state
sections). Phase-specific historical documents
(`docs/documentation_sync_report.md`,
`docs/postgresql_verification_report.md`, phase N deferral notes, and
README's Phase 1–7 era narrative) intentionally retain the facts of
their time and are excluded from current-state claims.

## 3. Dependency closure — classified

- **Directly declared and directly imported**: Flask, Flask-SQLAlchemy,
  Flask-Migrate, Flask-JWT-Extended, Flask-CORS, Flask-Limiter,
  marshmallow, psycopg[binary], python-dotenv, bcrypt, openpyxl,
  vaderSentiment, scikit-learn, reportlab, requests, beautifulsoup4,
  redis, gunicorn, waitress, **urllib3** (Phase 15.1: now explicitly
  pinned — it is directly imported by the SSRF connect-time guard in
  `app/services/collectors/security.py`; although `requests==2.33.1`
  always supplies it via its declared constraint `urllib3<3,>=1.26`,
  a security-boundary import is pinned directly rather than left to
  transitive resolution). pytest/pytest-flask are the test stack.
- **Supplied transitively, imported directly**: none remaining.
- **Optional by design**: `boto3` (S3 backend; absent intentional — mock-tested only).
- **Intentionally absent**: WeasyPrint (not installable on this Windows
  host; ReportLab is the PDF engine), Celery/Redis-as-broker (no job
  queue by design), LangGraph, Selenium/Playwright/Scrapy.

## 4. Exact change accounting (Phase 14 + 15 + 15.1)

Phase 14 (multi-instance closure): **4 files created**
(`backend/tests/test_redis_integration.py`,
`backend/scripts/phase14_distributed_verification.py`,
`backend/scripts/phase14_pg_dump_drill.py`,
`docs/production_configuration_matrix.md`); **8 files modified**
(`backend/requirements.txt`, `backend/.dockerignore`,
`backend/.env.example`, `docker-compose.yml`,
`backend/tests/test_rate_limiter_storage_wiring.py` (docstring),
`docs/production_deployment.md`, `docs/release_certification.md`,
`AGENTS.md`).

Phase 15 (freeze audit): **9 files modified** (`README.md`,
`backend/run.py`, `backend/.env.example`, `backend/scripts/phase12_env.sh`,
`backend/scripts/phase12_orchestrator.py`,
`backend/scripts/phase13_backup_drill.py`,
`docs/production_deployment.md`,
`docs/production_configuration_matrix.md`,
`backend/app/services/excel_report_service.py`); **1 untracked artifact
deleted** (`nul`, 0 bytes); **0 files created**.

Phase 15.1 (certification hardening): **4 files modified**
(`backend/requirements.txt` — explicit `urllib3==2.7.0` pin;
`README.md` — production-readiness answer scoped to the verified
deployment topology; `docs/release_rollback.md` — compose path marked
statically-validated-only; `docs/release_certification.md` — this
addendum). **0 created, 0 deleted.**

All other modified/untracked paths in `git status` are pre-existing
Phase 8–13 work, not owned by Phases 14–15.1. No commits were made.

## 5. Claim → evidence traceability

| Claim | Classification | Evidence source |
| --- | --- | --- |
| 400 backend tests pass | VERIFIED | `python -m pytest -q` (3× in Phase 15: 400/0/2 warnings each) |
| Frontend production build | VERIFIED | `npm run build` exit 0 (Phase 15 final batch) |
| Migration chain 0001→0009 | VERIFIED | `scripts/audit_migration_postgres.py` PASS (Phase 15 re-run) |
| End-to-end workflow | VERIFIED | `scripts/phase12_orchestrator.py` stages A–H ALL PASS (Phase 15 re-run, incl. PDF/Excel magic bytes) |
| Cross-instance JWT revocation | VERIFIED | `scripts/phase14_distributed_verification.py` stages 1–3 PASS (Phase 15 re-run) |
| Distributed rate limiting | VERIFIED | same script, stage 4 PASS (10 shared acceptances → 429 on both processes) |
| Real pg_dump/pg_restore round-trip | VERIFIED | `scripts/phase14_pg_dump_drill.py` PASS (Phase 15 re-run; exact snapshot ×2) |
| Python-level backup drill | VERIFIED | `scripts/phase13_backup_drill.py` PASS (Phase 15 re-run after credential refactor) |
| API contract coherence | VERIFIED (static mapping + runtime flow) | 117 frontend calls ↔ 94 route paths/methods all matched; orchestrator full workflow |
| Env-variable documentation coverage | VERIFIED (static) | audit scan: 52/52 code-read vars present in `.env.example` AND the matrix |
| Secret sweep | VERIFIED (static scan) | tracked-file scans clean; script credentials removed and re-verified by execution |
| Prototype isolation | VERIFIED | 20 prototype tests pass; zero production↔prototype imports added |
| Docker runtime / gunicorn / nginx containers | STATICALLY VALIDATED (ENVIRONMENT BLOCKED for execution) | YAML/Dockerfile inspection; no daemon on host |
| Trivy scan | NOT RUN — TOOL UNAVAILABLE | binary absent; operator command documented |
| S3 object storage | TESTED WITH MOCKS | 5 unit tests vs fake boto3 |
| TLS termination | DOCUMENTED | `docs/nginx_production.conf`; no domain/certs here |

## 6. Final deployment scope

**Verified scope**: on-host deployment — one or more application
processes (waitress on Windows, gunicorn on Linux-by-construction)
against one PostgreSQL 18.6; for >1 process/replica, Redis must back
`LIMITER_STORAGE_URL` and `REVOCATION_STORE_URL` (both runtime-verified
in that exact arrangement). Uploads/reports on the host filesystem
(single-instance) or a shared volume; S3 remains mock-tested.

**Outside the runtime-verified evidence set**: Docker/compose runtime,
gunicorn-in-container, nginx container, Trivy scanning, real S3, TLS
termination, multi-host HA/failover, zero-downtime deployment.
