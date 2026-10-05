# Decision Log

This log records decisions made for the customer/security-intelligence extension. Older architectural decisions remain in their phase-specific documents; no pre-existing rationale is reconstructed here.

## 2026-10-04 — Use Review rows as evidence and preserve duplicate links

- **Decision:** `Review.id` remains the canonical evidence identifier. Add directional duplicate relationships in a separate table; retain all source review rows.
- **Context:** Investigation findings need stable provenance across configured source adapters without duplicating feedback content.
- **Why:** Reusing reviews avoids a second content store, while explicit duplicate links retain each source's provenance and make canonical counts explainable.
- **Alternatives:** Copy all review content into a new evidence table; merge/delete duplicates; fuzzy clustering.
- **Trade-offs:** Detection is limited to source-scoped provider ID, sanitized URL, or exact normalized text hash; uncertain paraphrases remain separate.
- **Evidence:** `evidence_service.py`, `duplicate_detection_service.py`, migration `0015`.
- **Verification:** `tests/test_evidence_intelligence.py`; PostgreSQL migration audit.
- **Affected files:** Review evidence services, source statistics/reporting, migration `0015`.

## 2026-10-04 — Use deterministic time windows and indicators

- **Decision:** Emerging themes, anomalies, root-cause layers, security indicators and correlations are on-demand deterministic calculations over persisted reviews.
- **Context:** No evaluated semantic classifier, threat reputation feed, or causal model exists.
- **Why:** Explicit windows, phrase evidence, and conservative indicator states remain auditable without inventing confidence or incidents.
- **Alternatives:** Model-only classification, unsourced ATT&CK/STIX mapping, implicit causal conclusions.
- **Trade-offs:** Phrase/aspect coverage is partial; zero-baseline changes and sampled windows need visible limitations. No CTI/STIX export is provided.
- **Evidence:** temporal/root-cause/security intelligence services and response limitations.
- **Verification:** `tests/test_evidence_intelligence.py` and full regression suite.
- **Affected files:** Analysis services/routes, source/report panels, migration `0015` duplicate relation.

## 2026-10-04 — Persist investigations separately from synchronous workflows

- **Decision:** Add project/organization-scoped investigations, activities, and evidence-linked findings. Run investigations in a separate one-process worker using PostgreSQL conditional claims/leases and bounded retries.
- **Context:** Existing `agent_workflows` are synchronous deterministic orchestration; investigations need durable status and optional bounded LLM synthesis.
- **Why:** Separate persistence avoids changing workflow semantics, and database leases prevent simultaneous execution without introducing a queue service.
- **Alternatives:** Long HTTP request, in-memory daemon, new Redis/Celery queue, reuse `agent_workflows`.
- **Trade-offs:** The worker must be deployed and monitored separately; no-LLM mode returns deterministic summaries; external collection is explicitly outside investigator tools.
- **Evidence:** `investigation_service.py`, `investigation_tools.py`, models/migration `0016`, Compose worker.
- **Verification:** focused API/worker/security tests; PostgreSQL migration audit; live deployment remains unverified.
- **Affected files:** Investigation models/API/services/UI, CLI, Compose, docs, migration `0016`.

## 2026-10-04 — Bound LLM output to evidence-backed interpretations

- **Decision:** Reuse the configured text provider. Require strict JSON and allowed enums/statuses, validate every cited evidence ID against data retrieved during the job, and set confidence to null. Invalid/unavailable model output falls back to deterministic evidence summary.
- **Context:** External reviews are untrusted content, and no model confidence calibration is available.
- **Why:** Backend authorization and evidence services remain authoritative; the model has no arbitrary SQL/network/shell tools.
- **Alternatives:** Parse prose, persist hidden reasoning, trust model-provided IDs/confidence, fail all investigation work without a provider.
- **Trade-offs:** Only a finite registered tool set is available; semantic synthesis can be unavailable.
- **Evidence:** `investigation_service.py`, `investigation_tools.py`, schemas, adversarial validation tests.
- **Verification:** `tests/test_investigations.py` including malicious evidence and fabricated IDs; provider outage covered by deterministic worker path.
- **Affected files:** Investigation services, models/API, UI, tests.

## 2026-10-04 — Persist only bounded evidence-linked synthesis

- **Decision:** Remove duplicate raw text and source metadata from tool-result prompt payloads, minimize/redact a bounded evidence excerpt, and build the persisted answer from validated finding claims rather than the model's free-form answer field. A model may cite only IDs present in its actual bounded prompt.
- **Context:** Tool output may include user-supplied metadata/reviews and can otherwise repeat PII or text beyond the prompt context cap.
- **Why:** This reduces unnecessary external data disclosure and stops uncited standalone model prose from appearing as the investigation's result.
- **Alternatives:** Send complete tool payloads, truncate serialized JSON mid-object, persist free-form response verbatim.
- **Trade-offs:** Semantic context is intentionally partial; evidence links in validated findings remain the complete trace.
- **Evidence:** `investigation_service._compact_tool_result`, `_model_evidence_context`, `_synthesize`.
- **Verification:** Adversarial tests assert injection remains untrusted, duplicate tool text and email references are omitted, context is bounded, and uncited answer prose is discarded.
- **Affected files:** Investigation service/tests, flow and model-change docs.

## 2026-10-04 — Keep product/entity resolution deterministic and project-scoped

- **Decision:** Store one canonical entity per project and resolve normalized aliases and identifiers without network access or an LLM.
- **Context:** The existing project model holds a free-form product/topic string, which is insufficient for safe keyword matching and source selection.
- **Why:** Deterministic matching is auditable, cheap, and cannot make external requests based on a guessed entity.
- **Alternatives:** Runtime extraction from URL with an LLM; global entity catalog; multiple entity tables.
- **Trade-offs:** The user must correct ambiguous data; project-level one-entity design does not model a portfolio hierarchy.
- **Evidence:** `ProjectEntity`, `ProjectEntityService`, `EntityResolver`; migration `0010`.
- **Verification:** `tests/test_product_entity_intelligence.py`; PostgreSQL migration audit.
- **Affected files:** `backend/app/models/project_entity.py`, `backend/app/services/entity_resolver.py`, `backend/app/routes/projects.py`, migration `0010`.

## 2026-10-04 — Apply configured keywords at bounded points

- **Decision:** Apply inclusion/exclusion terms to records from the existing controlled collection path; apply the same vocabulary as annotations to file-imported records without silently dropping customer uploads.
- **Context:** Keywords were project metadata and did not affect ingestion. File imports and source collection have different user expectations.
- **Why:** Collection filtering can bound irrelevant external records, while silently discarding uploaded rows would risk data loss.
- **Alternatives:** Filter every ingestion source; add a keyword table; use arbitrary SQL search fragments.
- **Trade-offs:** Imported records remain stored even when they fail configured include/exclude rules; annotations expose matching terms.
- **Evidence:** `project_keyword_matching.py`, `CollectionService`, `dataset_service.py`, `Review.keyword_matches`; migration `0011`.
- **Verification:** `tests/test_project_keyword_matching.py`, `tests/test_collection.py`, full backend suite.
- **Affected files:** keyword service, collection/dataset services, review model/API serialization, migration `0011`.

## 2026-10-04 — Security signals are evidence-linked, deterministic observations

- **Decision:** Persist only supported phrase-rule signals, exact evidence spans, a rule identifier, and a nullable confidence; default to `needs_review`.
- **Context:** Feedback may mention security without proving an incident. No calibrated security classifier exists in the current application.
- **Why:** Evidence and uncertainty must remain visible; a made-up numeric confidence would imply calibration that is absent.
- **Alternatives:** Boolean flag on reviews; model-only classification; automatic incident escalation.
- **Trade-offs:** Rule coverage is limited and may miss paraphrases. Analysts must review findings.
- **Evidence:** `security_intelligence_service.py`, `SecurityFinding`, scoped security routes; migration `0012`.
- **Verification:** `tests/test_security_intelligence.py`; PostgreSQL migration audit.
- **Affected files:** security service/model/permission/routes/UI and migration `0012`.

### Evidence lifecycle follow-up

- **Decision:** Reconcile stored rule findings when a review changes. Store a SHA-256 fingerprint of the full review text; preserve previous evidence with a `stale` status if the current eligible text no longer matches, and clear the previous human decision whenever any part of matching review text changes.
- **Context:** Reviews are editable and can be marked spam/duplicate/deleted after a finding is confirmed. Leaving the old row as current would misrepresent its evidence.
- **Why:** Findings remain traceable without presenting outdated text as a current match. A stale row cannot be confirmed until analysis is rerun.
- **Alternatives:** Delete historical findings; leave all old decisions untouched; introduce a separate immutable evidence-version table.
- **Trade-offs:** This retains one current/stale finding per review/type, not a full revision history of every evidence change. The hash is a change detector, not a cryptographic proof of source authenticity.
- **Evidence:** `SecurityIntelligenceService` reconciliation and stale-state route guard.
- **Verification:** `tests/test_security_intelligence.py::test_reanalysis_marks_changed_evidence_stale_and_reopens_changed_match`.
- **Affected files:** security analysis service, finding model, project routes, security panel, migration `0013`, tests.

## 2026-10-04 — Add report trust and evidence without changing report storage

- **Decision:** Add an optional `securityFindings` report section, a bounded source-provenance appendix, and always render a methodology appendix with FACT, OBSERVATION, MODEL INTERPRETATION, HYPOTHESIS, and RECOMMENDATION definitions. Preserve existing PDF/Excel generation and storage boundaries.
- **Context:** Security signals need source traceability and reports must separate evidence from interpretation.
- **Why:** Existing report service already owns data gathering and formats; extending it avoids a parallel reporting path.
- **Alternatives:** Separate report product/API; place all security prose in optional model interpretation.
- **Trade-offs:** The appendix states that root cause is not established by this implementation. Model interpretations still exist only through the current report mode.
- **Evidence:** `report_data_service.py`, `pdf_report_service.py`, `excel_report_service.py`, `ReportsPage.jsx`.
- **Verification:** `tests/test_reports.py` validates both generated file formats, source URL secret stripping, provenance/methodology cells, date/exclusion filters, and Excel formula-marker escaping.
- **Affected files:** report services, reports frontend, report tests.

## 2026-10-04 — Use Vercel for the frontend and a persistent Flask backend

- **Decision:** Provide Vercel static SPA routing and keep the Flask API on a persistent container deployment.
- **Context:** The backend accepts large uploads, uses local staging/storage abstractions, performs potentially long synchronous workflows, and serializes collection with a process-local lock.
- **Why:** Current Vercel supports Flask, but function request bodies are limited to 4.5 MiB, this app accepts 25 MiB uploads, and function filesystems are read-only except temporary `/tmp`; the app also relies on process-local serialized collection and local-or-configured file storage. Deployment would require direct object-storage uploads, external reports, and distributed collection coordination first.
- **Alternatives:** Deploy the existing Flask app as one Vercel Function; redesign backend upload/storage/locking for Functions; retain a persistent Flask host.
- **Trade-offs:** Frontend and API have separate deployment/configuration surfaces. This decision can be revisited after the backend's storage and collection boundaries are externalized. A live deployment has not been verified.
- **Evidence:** `frontend/vercel.json`, `docs/vercel_frontend_deployment.md`, backend upload/storage/collection code, [Vercel Flask guide](https://vercel.com/docs/frameworks/backend/flask), [limits](https://vercel.com/docs/functions/limitations), [runtime](https://vercel.com/docs/functions/runtimes).
- **Verification:** Vite build and configuration/code review; no Vercel credentials or browser walkthrough were available.
- **Affected files:** Vercel config and deployment documentation.

## 2026-10-04 — Do not call thread-backed workflow execution durable

- **Decision:** Keep the existing workflow executor synchronous until durable resumability and collection coordination are designed together.
- **Context:** Maximum configured collection work can exceed the HTTP server timeout. `agent_workflows` persists final workflow/step summaries, but the deterministic and optional LangGraph runners execute synchronously and do not checkpoint after every step. Collection uses a process-local lock.
- **Why:** A background thread would stop on process restart and can race a second application replica; a separate worker would bypass the existing process-local collection lock. Neither is a verified durable job system.
- **Alternatives:** In-process daemon thread; separate polling process; broker/queue; DB claim plus cross-process collection lock.
- **Trade-offs:** Long workflows can still exceed request budgets; this is a documented blocker for reliable production-scale collection.
- **Evidence:** `workflow_service.start_workflow`, both orchestrators, `CollectionService`, Docker single-process deployment.
- **Verification:** Code-path inspection; no async execution capability is claimed.
- **Affected files:** Documentation only. Implementing a durable worker remains pending.

## 2026-10-04 — Derive competitor evidence from configured terms

- **Decision:** Add a project-scoped read endpoint and Project Details panel that match configured competitor phrases against current eligible reviews. Mark switching intent only when explicit switching language names that exact competitor as the destination; do not persist derived findings.
- **Context:** Competitor keywords were stored and annotated during ingestion but had no analysis or review surface.
- **Why:** This provides immediate evidence traceability without another table, stale-decision lifecycle, source search integration, or invented classifier confidence.
- **Alternatives:** LLM extraction; persist every mention; build a cross-source search router first.
- **Trade-offs:** Phrase-only matching misses aliases and paraphrases; reason snippets are attributed language rather than causal validation; list is bounded to 5,000 recent eligible reviews.
- **Evidence:** `competitor_intelligence_service.py`, `/analysis/competitors`, `CompetitorIntelligencePanel.jsx`.
- **Verification:** `tests/test_product_entity_intelligence.py` covers direct switching evidence, destination-specific matching, non-switch mention, sentence separation, spam exclusion, and cross-organisation hiding; frontend build.
- **Affected files:** Competitor service, analysis route, entity intelligence tests, Project Details panel/API, customer intelligence and flow docs.

## 2026-10-04 — Use bounded phrase rules for initial feedback categories

- **Decision:** Add a deterministic, multi-label category endpoint and Project Details view, using explicit phrase evidence and existing configured competitor/security terms. Derive results from current eligible reviews without a new table.
- **Context:** Customer feedback category labels were requested, but no trained/evaluated semantic classifier or LLM classification schema currently exists.
- **Why:** Explicit matches can be traced to exact review spans and work without external AI credentials. `OTHER` means no current rule matched, not a semantic conclusion.
- **Alternatives:** Add an LLM classification layer immediately; persist derived labels; omit categorization until model evaluation exists.
- **Trade-offs:** The rule vocabulary is partial, overlapping category counts do not sum to review volume, and paraphrases may be missed. Scan/result caps bound response work.
- **Evidence:** `feedback_intelligence_service.py`, `/analysis/feedback-categories`, `FeedbackCategoriesPanel.jsx`.
- **Verification:** `tests/test_product_entity_intelligence.py` asserts multiple categories, exact evidence spans, configured security terms, spam exclusion, and tenant scope; full suite and frontend build.
- **Affected files:** Feedback service, analysis route, entity-intelligence tests, Project Details UI/API, customer-intelligence and flow docs.

## 2026-10-04 — Add one fixed official GitHub Issues source adapter

- **Decision:** Support configured public GitHub repositories through the official REST API as one additional source type. Constrain repository identifiers to `github.com/{owner}/{repo}`, target only `api.github.com`, refuse redirects, exclude pull requests, omit author names, and honor the shared collector limits.
- **Context:** Product-level cross-source intelligence needs another source with a stable, documented API; unrestricted HTML crawling of community pages would increase policy, SSRF, and maintenance risk.
- **Why:** GitHub's public issues endpoint offers a bounded, testable source and gives explicit quota failures. Its results are technical community reports, so the UI/collector labels them as non-representative feedback.
- **Alternatives:** Generic arbitrary-URL/API adapter; more HTML scraping; defer all new source support.
- **Trade-offs:** This is a configured repository adapter, not product-wide discovery; public unauthenticated rate limits can stop collection. An optional server-side token improves quota headroom but does not unlock private repositories.
- **Evidence:** `GitHubIssuesCollector`, `CollectionService`, source registry and types; [GitHub REST Issues API](https://docs.github.com/en/rest/issues/issues) and [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
- **Verification:** Collector unit tests, authenticated API-to-review integration test, source-URL secret stripping test, PostgreSQL upgrade/downgrade/re-upgrade audit.
- **Affected files:** GitHub collector/registry, collection service, source/review models, migration `0014`, review UI, report provenance, tests and source/deployment docs.

## 2026-10-04 — Preserve bounded per-review collection provenance

- **Decision:** Persist provider record ID, safe item URL, bounded JSON source metadata, and collection timestamp directly on each collected `Review`; keep provider IDs non-unique so content revisions can still be ingested and flagged through existing duplicate semantics.
- **Context:** Collectors already normalized item references, but ingestion discarded them, preventing a report or analyst from tracing an individual finding to its source item.
- **Why:** Additive nullable fields preserve imported review compatibility and existing duplicate behavior while making collected evidence traceable. URL credentials, query, and fragment are removed; metadata above 8 KiB is discarded.
- **Alternatives:** New source-record table and relation; use only the generic DataSource URL; globally deduplicate and merge records.
- **Trade-offs:** Cross-source canonical evidence and merged duplicate provenance remain future work; metadata is bounded but adapter-specific.
- **Evidence:** `Review`, `_review_provenance`, report serialization and `ReviewManagement`.
- **Verification:** Collection/report regressions plus isolated PostgreSQL migration audit through `0014`.
- **Affected files:** Review model/service, migration `0014`, PostgreSQL audit script, review UI and report service/tests.

## 2026-10-04 — Load page bundles on route entry

- **Decision:** Convert route page components to `React.lazy` imports and wrap the route tree in an accessible `Suspense` status fallback.
- **Context:** The previous frontend build had one 580.04 kB minified application chunk and Vite warned that it exceeded 500 kB.
- **Why:** Page-specific code should load when the user opens that route; the existing dependency set did not need replacement.
- **Alternatives:** Raise Vite's warning limit; manually assign vendor chunks; remove dependencies without evidence.
- **Trade-offs:** Navigating to an unloaded page incurs a small chunk fetch; browser walkthrough could not be performed in this session.
- **Evidence:** `frontend/src/App.jsx` uses dynamic page imports and a `role="status"` fallback.
- **Verification:** `npm run build` passes; largest emitted JS chunk is 252.01 kB, and Vite emits no chunk-size warning.
- **Affected files:** `frontend/src/App.jsx`, flow and handoff documentation.
