# Model Changes — 2026-10-04 Implementation Cycle

This file records only this local implementation cycle. It is not a permanent architectural decision log.

## Database and backend

- Added `ProjectEntity`, a one-per-project canonical entity and keyword configuration model, with migration `0010_project_entity`.
- Added `Review.keyword_matches` JSON and migration `0011_review_keyword_matches`.
- Added `SecurityFinding` with organisation/project/review ownership, rule method, evidence, indicators, nullable confidence, analyst status/notes, and migration `0012_security_findings`.
- Added `security_findings.review_text_sha256` in migration `0013`; analysis now invalidates human review when any source-review text changes, marks no-longer-matching evidence stale, and blocks stale confirmation.
- Added deterministic entity resolver, project entity service/schema/API, keyword matcher, and evidence-linked rule-based security intelligence service/API.
- Added `review_security_findings` permission grants consistent with existing analyst/editor roles.
- Extended PDF/Excel report generation with bounded source provenance, security evidence/provenance, and the methodology/trust appendix. Excel exports escape formula-like untrusted text as literal values.
- Corrected representative-review report shape and filtering: source/date fields now match the renderer, and examples obey report date bounds plus deleted/spam/duplicate exclusions.
- Made the S3 missing-dependency test independent of ambient boto3 installation.
- Added derived competitor mention/switching analysis over configured project terms. It preserves evidence spans and review/source references, excludes ineligible reviews, and marks a switch only when the named destination is that competitor; it adds no persistence schema.
- Added a bounded multi-label deterministic feedback categorizer covering customer and security categories. It includes exact evidence spans, category counts, project-configured security/competitor terms, and `OTHER` only when no phrase rule matched.
- Added `GitHubIssuesCollector`, registered as the `github_issues` source type. It queries only the official public GitHub Issues API for explicitly configured repositories, filters pull requests, refuses redirects, enforces existing collection bounds, and reports provider rate limits/access failures. Optional `GITHUB_TOKEN` remains server-side.
- Added migration `0014_review_source_provenance` to retain provider record IDs, sanitized item URLs, bounded metadata, and collection timestamps on collected reviews. Review API payloads and the review table expose traceable source links; security reports use the item URL when available.
- Added source API collector, collection-to-review provenance, secret-stripping, report-linkage, and migration-audit coverage. PostgreSQL audit now also verifies provenance index creation/removal.
- Split page modules behind React Router route usage via `React.lazy` and added an accessible `Suspense` status fallback. Largest built JS chunk fell from 580.04 kB to 252.01 kB; build no longer emits the 500 kB chunk warning.

## Frontend and deployment

- Added entity/keyword configuration and security findings panels to existing Project Details; added source-review navigation support.
- Added competitor evidence panel to Project Details, including loading/error/empty states, explicit method limitations, and source-review links.
- Added feedback category panel with per-category counts, evidence snippets, source-review links, and classifier limitations.
- Added `frontend/vercel.json` for Vite SPA deep-link routing and documented frontend-only Vercel deployment.

## Migration audit

- Updated the PostgreSQL migration audit to use an isolated uniquely named schema and verify upgrade, downgrade to 0009, and re-upgrade for 0010–0013.

## Documentation

- Added customer/cyber implementation status, actual flow, decision log, this change record, and a 12-section handoff.
- Updated README/AGENTS/deployment docs to distinguish the unreleased working-tree schema from the deployed 0009 baseline.

## Tests and verification

- Added entity/API/tenant tests, keyword filtering/annotation tests, security evidence/tenant tests, report trust/provenance tests.
- Historical backend run immediately after the source-fingerprint addition: 453 passed, 0 failed, 2 warnings in 649.94s; it preceded the competitor follow-up recorded below. The entity URL credential rejection was tested immediately afterward in isolation and passed.
- Focused security suite after stale-evidence reconciliation: 5 passed.
- Final report-focused suite before the source-fingerprint addition: 19 passed.
- PostgreSQL migration audit through `0013` passed; downgrade to `0009` and re-upgrade verified.
- Frontend production build after stale-evidence UI copy: passed, 171 modules; main output chunk 573.68 kB with Vite's advisory warning.
- `git diff --check`: no whitespace errors; only expected LF-to-CRLF checkout notices.
- Real browser walkthrough and live deployment were unavailable/not performed.

### Competitor intelligence follow-up

- Added regression tests for explicit switch language, destination-specific matching, ordinary competitor mentions, sentence separation, spam exclusion, and tenant scoping.
- Targeted backend verification: 9 tests in `test_product_entity_intelligence.py` pass.
- Final full backend verification after the false-positive fix: 457 passed, 0 failed, 2 warnings in 559.50s.
- Frontend production build: passed with 173 transformed modules; final JS chunk 576.72 kB (Vite advisory remains).

### Feedback category follow-up

- Added `/api/v1/projects/{id}/analysis/feedback-categories` and a Project Details panel. Categories are multi-label phrase matches over existing eligible reviews, with source spans and deterministic counts.
- Configured security and competitor terms participate. The endpoint scans up to 5,000 reviews and returns at most 500 evidence records; no persistence migration was added.
- This category vocabulary is partial and not a semantic classifier. Final full backend verification: 459 passed, 0 failed, 2 existing warnings in 428.17s.
- Final frontend production build: passed with 175 transformed modules; JS chunk 579.65 kB (Vite size advisory remains).

## Evidence intelligence and investigation phase (local, unreleased)

- Added Review-ID evidence serialization, project-scoped duplicate links, exact cross-source duplicate detection, and source composition counts. Source rows remain independently stored.
- Added date-window emerging-theme/anomaly comparisons, layered root-cause evidence, syntax-only security indicator extraction, and cautious repeated-indicator correlation.
- Added persisted investigation, activity, and finding models/migrations; project-scoped create/list/get/cancel/review APIs; registered authorized tools; deterministic no-LLM fallback; strict JSON and evidence-ID validation; and bounded PostgreSQL lease worker.
- Added a lazy investigation workspace and selected-investigation PDF/Excel report section; report source appendix includes canonical/duplicate counts and source sampling limitations.
- Added focused tests for evidence, duplicate relationships, temporal comparison, security correlation, worker lifecycle, cancellation, tool validation, prompt-injection content boundary, malformed/fabricated model evidence, and reporting.
- Added a Compose worker service and documented startup/configuration. Production migrations and deployment remain unverified.
- Hardened investigation prompt assembly: raw tool-result text/URLs/metadata are omitted from the model request; a small redacted evidence excerpt remains explicitly untrusted. Model answers are composed only from validated evidence-linked findings, and citations must be among evidence IDs actually included in the bounded prompt. Per-request model tokens and timeouts are bounded.
- Tightened running-job cancellation semantics: only queued/waiting jobs are atomically cancelled; the UI explains that a claimed model call cannot be interrupted. Stale/dismissed security evidence is excluded from active indicator correlation.

### GitHub Issues / item-provenance follow-up

- Added fixed official REST collection for public GitHub repository issues. Pull requests are excluded, author names are not stored, and collection warns that issue reports are not representative consumer reviews.
- Persisted bounded per-review source provenance in migration `0014`; credentials/query/fragment are stripped from item URLs and oversized metadata is discarded.
- Added visible source links to review management and item-level links to security report evidence. Cross-source canonical deduplication remains unimplemented.
- Focused API/collection/report test run: 8 passed in 10.82 seconds. Isolated PostgreSQL 18.6 migration upgrade/downgrade/re-upgrade through `0014`, including index checks: passed. Frontend build passed (176 modules), largest JS chunk 252.01 kB, without Vite's size warning.
- Full backend verification after provenance edge-case checks: `466 passed, 0 failed, 2 existing warnings` in 390.53 seconds.
- Browser walkthrough is not verified: this session has no connected browser. Live Vercel and Docker deployment were not performed.
