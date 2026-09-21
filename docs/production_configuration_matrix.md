# Production Configuration Matrix

Canonical reference for every environment variable the backend reads.
`backend/.env.example` is the operator-facing copy; this matrix adds
the *required/optional*, *security impact*, and *multi-instance*
classification in one place. `docker-compose.yml` forwards the
deployment-relevant subset. Keep all three in sync.

**Convention:** "Required in prod" means `FLASK_ENV=production` refuses
to boot without it (`ProductionConfig.validate_environment`). Anything
not listed as required has a safe development default.

## Core

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `FLASK_ENV` | yes (implicit) | `development` | Must be `production`; selects `ProductionConfig` | Disables debug, enables env validation |
| `DEBUG` | no | `True` (dev) | Forced `False` | Debug mode would expose internals |
| `SECRET_KEY` | **yes** | dev placeholder | Random ≥32 bytes; dev defaults (`change-me`, `dev-`) rejected at boot | Signs Flask-side artifacts |
| `JWT_SECRET_KEY` | **yes** | dev placeholder | Random ≥32 bytes, distinct from `SECRET_KEY` | Compromise = arbitrary token forgery |
| `DATABASE_URL` | **yes** | localhost Postgres dev DB | `postgresql+psycopg://…`; pooled (`pre_ping`, recycle) | Holds all tenant data |
| `FRONTEND_URL` | no | `http://localhost:5173` | CORS fallback origin when `CORS_ALLOWED_ORIGINS` unset | Overly broad value weakens CORS |

## CORS / proxy

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `CORS_ALLOWED_ORIGINS` | recommended | unset (uses `FRONTEND_URL`) | Comma-separated exact origins; no wildcards | Wrong value opens credentialed cross-origin access |
| `TRUSTED_PROXY_COUNT` | recommended | `0` | Number of trusted proxy layers for `X-Forwarded-*` | Too high = client IP spoofing; defeats rate limiting |

## Rate limiting

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `RATE_LIMIT_ENABLED` | no | `true` | `false` disables the limiter entirely | Disabling removes brute-force protection |
| `LIMITER_STORAGE_URL` | **yes for multi-instance** | `memory://` | `redis://host:6379/db` shares buckets across replicas; `memory://` = per-process budgets | Per-instance budgets multiply attacker's allowed brute-force rate by replica count |
| `RATE_LIMIT_DEFAULT` | no | unset | Not wired to a default limit by design (see `app/limiter.py`); health endpoints must stay unthrottled | Setting a global default would break health probes |

## Token revocation (multi-instance)

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `REVOCATION_STORE_URL` | **yes for multi-instance** | unset (in-memory) | `redis://…` / `rediss://…`; unknown schemes fail boot; Redis outage fails closed (treats tokens as revoked) | Without it, logout/refresh revocation is per-process only — revoked tokens stay valid on other replicas |
| `REVOCATION_STORE_PREFIX` | no | `sams:revoked:` | Redis key namespace | Lets multiple deployments share one Redis safely |

## Observability

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `LOG_JSON` | no | `true` | One JSON object per line, request-id attached | Logs never contain secrets by design |
| `LOG_LEVEL` | no | `INFO` | `WARNING` in quiet environments | — |

## Database pool (production only)

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `DB_POOL_SIZE` | no | `5` | SQLAlchemy pool size | Too high exhausts Postgres connections |
| `DB_POOL_MAX_OVERFLOW` | no | `5` | Overflow connections | same |
| `DB_POOL_RECYCLE_SECONDS` | no | `1800` | Connection recycle interval | Prevents stale-connection stalls |

## Storage

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `STORAGE_BACKEND` | no | `local` | `local` = filesystem under `UPLOAD_FOLDER`/`REPORT_OUTPUT_DIRECTORY`; `s3` = object storage (mock-tested only) | Multi-instance requires shared volume or object storage |
| `S3_BUCKET` | required iff `STORAGE_BACKEND=s3` | unset | Target bucket | Wrong bucket = cross-environment data mixing |
| `S3_REGION` | no | `us-east-1` | Bucket region | — |
| `S3_ENDPOINT_URL` | no | unset | MinIO/R2 override | HTTPS endpoint required for non-AWS |
| `S3_KEY_PREFIX` | no | unset | Object key prefix | Namespace isolation when sharing a bucket |
| `S3_ACCESS_KEY_ID` | required iff s3 | unset | Static credential | **Secret — never commit** |
| `S3_SECRET_ACCESS_KEY` | required iff s3 | unset | Static credential | **Secret — never commit** |
| `UPLOAD_FOLDER` | no | `<instance>/uploads` | Upload root; 25 MiB cap enforced separately | Must be a non-public, application-owned path |
| `REPORT_OUTPUT_DIRECTORY` | no | `<instance>/reports` | Report output root | same |

## LLM (optional; deterministic fallback always available)

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `LLM_PROVIDER` | no | `deterministic` | `deterministic` / `openai_compatible` / `stub` | LLM failure must never break analysis (verified) |
| `LLM_BASE_URL` | required iff `openai_compatible` | unset | Chat-completions endpoint | SSRF-adjacent: operator-controlled only |
| `LLM_API_KEY` | required iff `openai_compatible` | unset | Bearer credential | **Secret — never commit** |
| `LLM_MODEL` | required iff `openai_compatible` | unset | Model name | — |
| `LLM_TIMEOUT_SECONDS` | no | `20` | Per-call timeout | Bounds worst-case request latency |
| `LLM_MAX_TOKENS` | no | `512` | Response cap | Bounds spend |

## Sentiment engine

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `SENTIMENT_ENGINE` | no | `vader` | `vader` (production) / `stub` (test only) | `stub` must never be used for real analysis |

## Web collection (scraping)

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `SCRAPER_REQUEST_TIMEOUT_SECONDS` | no | `15` | Per-request timeout | Bounds collector hang time |
| `SCRAPER_REQUEST_DELAY_SECONDS` | no | `1` | Politeness delay | Under-delaying can get the org blocked |
| `SCRAPER_MAX_PAGES` / `SCRAPER_MAX_RECORDS` | no | `10` / `500` | Collection bounds | Bounds resource use per run |
| `SCRAPER_MAX_RESPONSE_MB` | no | `5` | Response size cap | Prevents memory exhaustion |
| `SCRAPER_MAX_RETRIES` / `SCRAPER_MAX_REDIRECTS` | no | `2` / `5` | Fetch policy | Redirect revalidation stays on |
| `SCRAPER_USER_AGENT` | no | project bot UA | Identification header | Honest identification; do not spoof |
| `SCRAPER_ALLOW_PRIVATE_TARGETS` | no | **`false`** | DANGEROUS: disables SSRF private-network block. Env-only; never request/agent controlled | **Enabling in any internet-reachable env is a P0 SSRF exposure** |
| `SOURCE_FALLBACK_DISCOVERY_MODE` | no | `CURATED_ONLY` | Discovery metadata-only | Execution remains curated-registry-only |

## Reddit (optional)

| Variable | Required in prod | Dev default | Production behavior | Security impact |
| --- | --- | --- | --- | --- |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | no | unset | Enables Reddit OAuth collection path | **Secrets — never commit** |
| `REDDIT_USER_AGENT` | no | `SentimentAnalysisSystem/1.0` | Identifiable UA for the Reddit fallback | Honest identification only |

## Analysis tuning (all optional)

| Variable | Dev default | Behavior | Security impact |
| --- | --- | --- | --- |
| `DEFAULT_TOPIC_COUNT` | `8` | Default topic clusters per run | — |
| `MAX_TOPIC_COUNT` | `20` | Hard cap on requested topic count | Bounds compute per request |
| `KEYWORD_BLOCKED_WORDS` | unset | Extra stopwords for keyword extraction | — |
| `RECOMMENDATION_MIN_FREQUENCY` | `3` | Aspect-frequency floor for recommendation candidates | — |
| `MAX_REPORT_REVIEW_ROWS` | `500` | Cap on representative reviews embedded per report | Bounds report size/memory |
| `DEFAULT_ALERT_WINDOW_DAYS` | `7` | Default lookback window for alert metrics | — |

## Server runtime (waitress runner; Docker uses gunicorn)

| Variable | Dev default | Behavior | Security impact |
| --- | --- | --- | --- |
| `PORT` | `5000` | Bind port for `python -m app.runner` | — |
| `BIND_ADDRESS` | `0.0.0.0` | Bind address | Bind `127.0.0.1` when fronting locally |
| `WEB_CONCURRENCY` | `4` | Waitress thread count | Bounds per-process concurrency |

## Testing

| Variable | Default | Behavior |
| --- | --- | --- |
| `TEST_DATABASE_URL` | `sqlite:///:memory:` | Test-suite database override; production never reads it under `FLASK_ENV=production` |

## Experimental (leave alone)

| Variable | Default | Behavior |
| --- | --- | --- |
| `SOURCE_FALLBACK_DISCOVERY_MODE` | `CURATED_ONLY` | Metadata-only discovery for the controlled source-fallback registry; execution stays curated |

## Frontend (build-time)

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | no | `/api/v1` | Baked into the bundle at `npm run build`; works with the bundled nginx proxy |

---

## Verified deployment profiles

| Profile | Stores | Verification |
| --- | --- | --- |
| Single instance | `memory://` limiter + in-memory revocation | Full pytest + Phase 12/13 runtime |
| Multi-instance (this phase) | `redis://` limiter DB + `redis://` revocation DB + shared Postgres | `scripts/phase14_distributed_verification.py` PASS on two waitress processes + Redis 5.0.14.1 |
| Containerized single instance | same as single, inside compose | **ENVIRONMENT BLOCKED** (no Docker daemon here); statically valid |
