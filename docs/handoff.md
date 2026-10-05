# Developer Handoff

## 1. Current State

The repository contains the existing multi-tenant Flask/React sentiment application plus unreleased local changes for project entities/keywords, source provenance, security findings, duplicate links, temporal intelligence, persisted investigations, an official GitHub Issues adapter, and report provenance. Working-tree schema head is `0016`; the documented deployed baseline is `0009`. No commit or push has been made in this phase.

## 2. Product and Architecture

Frontend: React/Vite/React Router/Bootstrap/Chart.js. API: Flask under `/api/v1`, SQLAlchemy, Alembic, JWT, RBAC, organisation/project scoping. PostgreSQL is the production target. Existing deterministic analytics, reports, collectors, and synchronous agent workflow services remain the foundation.

## 3. Work Completed in This Cycle

- Product/entity metadata, deterministic resolver, validated project API and UI.
- Project include/exclude/security/competitor/custom terms; collection filters matching external records and dataset imports receive annotations.
- Deterministic configured-phrase competitor mentions and explicit switching evidence at `GET /api/v1/projects/{id}/analysis/competitors`, shown in Project Details. A switching signal names that competitor as destination. This is read-time analysis over at most 5,000 eligible stored reviews; it is not external search.
- Multi-label deterministic feedback categories at `GET /api/v1/projects/{id}/analysis/feedback-categories`, shown in Project Details with evidence, counts, and configured security/competitor terms. It scans up to 5,000 reviews and returns at most 500 evidence records; its phrase vocabulary is partial.
- Rule-based security feedback signals with exact evidence, provenance, triage status, tenant checks, and an existing Project Details workspace.
- Security findings, source-review fingerprint reconciliation, and methodology/trust labels in PDF/Excel reports.
- Vite SPA rewrite configuration and frontend-only Vercel deployment documentation.
- Official GitHub Issues REST API source type for public repository issue collection; not generic source discovery.
- Bounded item-level source record ID, sanitized source URL, adapter metadata, and collection timestamp on collected reviews; source links are surfaced in review management and reports.
- `Review.id` evidence service, conservative exact cross-source duplicate links, source statistics, temporal emerging/anomaly analysis, layered root-cause evidence, syntax-only security indicators and possible-incident correlation.
- Persisted investigation API/workspace with finite authorized tools, strict structured LLM validation, deterministic fallback, PostgreSQL lease worker and human review state.
- PDF/Excel investigation reporting and source canonical/duplicate composition; Compose starts one separate investigation worker.
- PostgreSQL audit extended through migrations `0015` and `0016` (must be rerun on this current tree before release).
- Separate decision, flow, model-change, customer/cyber-status, and handoff documents.

## 4. Important Decisions

See [decisions.md](decisions.md). Notably, entity resolution and security detection are deterministic; security confidence remains null because no calibration exists. Vercel is documented for the static frontend only. No daemon thread is called durable workflow processing.

## 5. Data and Migration State

Migration chain is `0001 -> ... -> 0016`. Migration `0015` adds `review_duplicate_links`; `0016` adds `investigations`, `investigation_events`, and `investigation_findings`. Earlier additions include `project_entities`, `security_findings`, review keyword/provenance fields, and security review fingerprint. Do not edit migrations `0001`–`0014`. Run `python scripts/audit_migration_postgres.py` against PostgreSQL before release. Production has not been migrated; apply migrations before deploying new API/worker code.

## 6. API and Frontend

- Project entity: `GET/PUT /api/v1/projects/{project_id}/entity`.
- Competitor evidence: `GET /api/v1/projects/{project_id}/analysis/competitors`, protected by project access and `view_reviews`.
- Feedback categories: `GET /api/v1/projects/{project_id}/analysis/feedback-categories`, protected by project access and `view_reviews`.
- Source composition/duplicates, temporal intelligence, root-cause evidence, indicators and correlation are under `/api/v1/projects/{project_id}/analysis/...` and require project access plus `view_reviews`.
- Investigation routes under `/api/v1/projects/{project_id}/investigations`: create, list, get, cancel queued/waiting jobs, and review finding. Claimed running jobs cannot be cancelled mid-provider call. `investigations-worker` CLI claims queued rows via PostgreSQL leases.
- Security: `GET /api/v1/projects/{project_id}/security-findings`, `POST .../analyze`, and `PATCH /api/v1/projects/{project_id}/security-findings/{finding_id}`; analysis adds observed indicators and cautious repeated-indicator correlation.
- Security routes require the new `review_security_findings` permission, project access, and audit relevant mutations.
- UI is embedded in existing Project Details; no new top-level page was introduced.
- Report section keys include `securityFindings` and `investigationFindings`; select an eligible completed investigation to include its validated evidence-linked findings in PDF/Excel.
- GitHub collection uses an existing source endpoint with `type: "github_issues"` and a repository URL such as `https://github.com/owner/repo`; optional `GITHUB_TOKEN` is server-side only.

## 7. Security Boundaries

Keep all collection inside `CollectionService`. Preserve SSRF checks, source policy, response/page/timeout caps, redirect validation, and serialized collection behavior. GitHub's adapter only targets the fixed official API host and refuses redirects. External reviews are untrusted content. Investigation tools are read-only, finite, project scoped, and do not perform collection/network fetches. LLM claims require returned evidence IDs and validated schema; model confidence is null. Security indicator observations do not verify maliciousness or incidents. Cross-tenant resource access must remain hidden and tested.

## 8. Tests and Verification

- Final demo-readiness full backend regression: `484 passed, 0 failed, 2 existing warnings` in 546.14s.
- `python -m compileall -q app migrations/versions scripts`: passed after final backend edits.
- Focused GitHub/provenance/report verification: `8 passed` in 10.82s.
- `test_product_entity_intelligence.py`: `11 passed`, covering entity config, competitor evidence/destination matching, category evidence/security keywords, spam filtering, and tenant scope.
- Report-focused suite: `19 passed` on the final report code.
- PostgreSQL 18.6 migration audit through `0016`: upgrade, downgrade to `0009`, and re-upgrade passed in isolated schema. New production migrations have not been applied.
- Frontend Vite build after investigation UI/report integration: passed (179 modules), largest JS chunk 252.35 kB; no Vite chunk-size warning.
- Local Docker runtime: isolated PostgreSQL 18, Redis, API, frontend, migration service, and investigation worker started. Fresh migration through `0016`, health/readiness, authenticated import/analysis, one persisted investigation claimed/completed by the worker, and report download were verified. This does not certify production deployment.
- `git diff --check`: no whitespace errors; Git prints line-ending conversion notices for the repository's configured CRLF checkout.
- Two backend warnings are pre-existing test warnings: legacy SQLAlchemy `Query.get()` use in `test_report_modes.py`, and the deliberate duplicate `ReviewTopic` constraint exercise in `test_topics.py`.
- Browser walkthrough: attempted, but no in-app browser runtime was available; therefore not performed. Live Vercel/production deployment and live LLM provider were not performed.

## 9. Deployment State

The frontend-only Vercel rewrite exists; no live Vercel project was deployed. An isolated local Compose runtime was verified against PostgreSQL 18, including migration `0016` and worker completion. The Flask backend remains intended for the existing persistent container/operator deployment. New migrations are not released to production. The in-app browser capability was unavailable in this coding session.

## 10. Known Limitations

The investigator uses deterministic planning by default and optional structured synthesis; it is not an autonomous web researcher. The local demo verified only deterministic fallback; no live provider was configured/tested. Feedback categorization and temporal themes are phrase/aspect based and partial. Duplicate matching is exact-only. Security indicators are syntax observations without reputation, CTI/STIX export or ATT&CK mapping. Production migrations/deployment remain unverified. Competitor analysis reads only configured phrases in already-ingested data.

## 11. Environment and Commands

From `backend`:

```powershell
python -m pytest -v
python scripts/audit_migration_postgres.py
flask --app run db upgrade head
```

From `frontend`:

```powershell
npm run build
```

Use `backend/.env.example` and the deployment guides for environment configuration. Never commit `.env`, credentials, generated reports, uploads, databases, or build output.

## 12. Exact Continuation Point

1. Before release, perform a real-browser walkthrough of entity configuration, security finding review, linked source review, report selection/download, and permission-denied states.
2. Review and release migrations `0010`–`0017` only after approval of the schema rollout; upgrade the target database before deploying new API/worker code.
3. Run an authenticated browser walkthrough when an in-app browser session is available. Validate login, project settings, source/data import, temporal/security views, investigation lifecycle, evidence navigation, and report generation.
4. Do not deploy or migrate production without an explicit release request.

## 13. Final Demo-Readiness Pass (2026-10-04)

- Started an isolated Docker Compose project `sams-demo-readiness-20261004` using ignored root file `.env.demo.local`; it uses a fresh PostgreSQL 18 named volume and does not read the backend `.env` or connect to production. The Compose stack is intentionally left running for the demo on frontend port `8082` and API port `5000`.
- Corrected the PostgreSQL 18 volume mount in `docker-compose.yml` from the legacy nested data directory to `/var/lib/postgresql`; this was prompted by an actual fresh-container startup failure. Added `FRONTEND_PORT` override because host port `8080` was already occupied by an unrelated local application. The unrelated service was left untouched.
- Fresh Compose migration job completed through `0016`; `flask db current` in the running API container reports `0016 (head)`. PostgreSQL, Redis, API, and frontend health checks are healthy; the worker container remains running.
- Created local demo login `demo@example.test` and project `Demo Phone Intelligence — DEMO DATA`. Imported `database/demo_intelligence_dataset.csv` after correcting three malformed CSV quoting rows; the processed dataset contains 23 synthetic demo records. The source labels explicitly state `DEMO DATA`; nothing represents live external customer data.
- Runtime API checks returned 23 analyzed reviews (15 positive, 6 neutral, 2 negative); four competitor mentions with two explicit destination switches and two non-switch mentions; one emerging theme and two temporal anomalies over baseline `2026-09-21..2026-09-27` vs current `2026-09-28..2026-10-04`; four deterministic security findings, four observed syntax indicators, and two `POSSIBLE_INCIDENT` correlations. No incident is confirmed. There are 23 source records and zero duplicate relationships in this fixture.
- A real investigation was queued, claimed by the running worker, and completed in one attempt. It has six recorded tool activities and a persisted evidence-linked observation referencing 23 review IDs. LLM mode was deterministic fallback: semantic synthesis reports `unavailable`; no live provider was tested.
- Generated and downloaded PDF and Excel reports with investigation findings selected. Both responses were HTTP 200 and had valid file signatures (`%PDF-` and `PK`); both report records reached `complete`.
- Authenticated API checks covered login, project/entity, review list, sentiment summary, competitors, feedback categories, source statistics, emerging themes, anomalies, security findings/indicators/incidents, investigation list, and report generation/download. Unauthenticated analysis returned 401; an unknown project returned 404. Frontend root/login/nested project paths returned the SPA HTML fallback and the production bundle built; this is HTTP/static verification, not browser rendering.
- Fixed a verified source-level CSS hit-area defect on login: the transparent lamp-pull button overlapped the submit panel. Its invisible area no longer captures clicks; the visible cord/handle remain pointer targets. The browser runtime was unavailable, so mouse behavior remains not browser-verified.
- Full backend regression: `484 passed, 0 failed, 2 existing warnings` in 546.14s. Frontend production build: 179 modules, largest JS chunk 252.35 kB on local Vite build; rebuilt Compose frontend chunk 252.33 kB. Both succeeded without a chunk-size warning. Final `git diff --check` passed (Git emitted only the configured LF-to-CRLF checkout notices). PostgreSQL container runtime and worker claim/completion were exercised locally; this does not certify production. Browser, Vercel/live deployment, and live LLM provider remain unverified.

### Demo startup

The current isolated demo stack is already running. Open `http://localhost:8082` and sign in with the local-only demo account; use the `Demo Phone Intelligence — DEMO DATA` project. The disposable login details are provided directly for this recording and are intentionally omitted from tracked files. To restart the existing stack from the repository root: `docker compose --env-file .env.demo.local --project-name sams-demo-readiness-20261004 up -d`. Stop it without deleting its demo database with `docker compose --env-file .env.demo.local --project-name sams-demo-readiness-20261004 down`.

## 14. URL-first collection and optional date filters (local, unreleased)

- Data source creation accepts a URL without a source type; the backend infers a registered collector. The UI immediately starts collection after source creation. Amazon India sign-in responses stop Amazon requests and may proceed only to the independent approved fallback providers.
- Report and summary date bounds are optional, including one-sided ranges. Migration `0017` makes the stored dates nullable; it has not been applied to the running demo database or production.
- Verification: backend suite `514 passed, 0 failed, 2 warnings` in `613.31s`; after the final discovery-prompt adjustment, focused product-discovery and collection suites passed (`29 passed`). Frontend build passed (179 modules); `/api/v1/health` returned HTTP 200 through local frontend ports 5173 and 8082. This did not include a real-browser walkthrough or PostgreSQL migration audit for head `0017`.
- The running Compose demo remains on API/schema head `0016`; it was not rebuilt or migrated. The Vite frontend on `5173` and its API health route are reachable, but the running API does not yet contain the new source/date behavior. Apply migration `0017` and run the current backend locally before exercising these changes end to end.
