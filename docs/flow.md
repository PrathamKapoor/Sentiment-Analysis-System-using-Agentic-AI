# Actual Application Flow

This document describes the checked-in implementation, including the customer/security intelligence extension in this working tree. It does not describe proposed adapters or agent tools as if they already exist.

## Request and authorization

1. React Router loads page components on demand through `React.lazy` inside an accessible `Suspense` loading state. Page routes call service modules under `frontend/src/services/`; the shared Axios client sends requests to `/api/v1` and attaches the current access token.
2. Flask registers blueprints in `backend/app/routes/`. Authentication decorators load the user from JWT; project/resource decorators resolve organisation membership and hide cross-tenant resources with `404` where that is the established contract.
3. Route handlers validate request JSON with Marshmallow schemas, then call a service. Services own business logic and use SQLAlchemy models through `db.session`.
4. Important state changes call `audit_service.log_action`. Response serialization uses the existing success/error envelope.

## Product entity and keywords

```text
Project Details
  -> entityApi.get(projectId)
  -> GET /api/v1/projects/{id}/entity
  -> project route + project-access decorator
  -> ProjectEntityService.get_or_resolve()
  -> saved ProjectEntity or deterministic values from existing project fields
```

`PUT /api/v1/projects/{id}/entity` validates brand/product/model/SKU, aliases, identifiers, and include/exclude/security/competitor/custom keyword lists. `ProjectEntityResolver` normalizes URL/text and matches only the stored project entity; it does not perform network lookup or call an LLM.

During website collection, the existing route enters `CollectionService`. The service checks project/source policy, invokes the existing permitted collector, normalizes its result, applies `ProjectKeywordMatcher`, inserts only matching source records, and persists match annotations on saved reviews. Dataset imports retain their rows and store keyword annotations rather than dropping rows.

For a `github_issues` source, `CollectionService` selects `GitHubIssuesCollector`. The adapter accepts only `https://github.com/{owner}/{repo}` as an identifier, fixes all requests to `https://api.github.com`, validates the API destination against SSRF rules, disables redirects, bounds pages/records/bytes/time/retries, skips pull-request records, and maps provider quota failures to `COLLECTION_RATE_LIMITED`. Collection persists each normalized issue's numeric ID, canonical issue URL, bounded metadata, and retrieval timestamp on `Review`; names are omitted. Source-item URLs are sanitized again on ingestion and when serialized in reports.

## Competitor and switching evidence

```text
Project Details / competitor panel
  -> competitorApi.get(projectId)
  -> GET /api/v1/projects/{id}/analysis/competitors
  -> project_access_required + view_reviews
  -> get_competitor_intelligence(project_id)
  -> ProjectEntity.competitor_keywords + eligible Review rows (max 5,000)
  -> literal phrase matches + explicit switching phrase checks per sentence
  -> response evidence spans, source origin, stored sentiment, counts, limitations
```

The service derives one record per review/competitor pair and preserves all matching spans. A switch must explicitly name that competitor as the destination; a mere mention in a sentence containing other switching language does not qualify. The optional `reason` is an attributed phrase following `because`, `since`, or `as`, not a validated cause. This read path does not persist derived results or invoke an LLM.

## Feedback category evidence

```text
Project Details / feedback category panel
  -> feedbackIntelligenceApi.categories(projectId)
  -> GET /api/v1/projects/{id}/analysis/feedback-categories
  -> project_access_required + view_reviews
  -> get_feedback_categories(project_id)
  -> eligible Review rows (max 5,000)
  -> deterministic category phrases + configured security/competitor terms
  -> exact evidence spans, source origin, category counts (max 500 records)
```

`classify_feedback` can return multiple phrase-backed categories for one review. Existing `extract_security_signals` rules are reused for security/privacy/fraud classifications. The service does not claim semantic completeness, does not persist labels, and does not expose model confidence. `OTHER` is a no-rule-match result.

## Security feedback findings

```text
Project Details security panel
  -> securityFindingApi
  -> GET/POST/PATCH /api/v1/projects/{id}/security-findings[...]
  -> auth + project membership + review_security_findings permission
  -> SecurityIntelligenceService
  -> explicit phrase rules over eligible non-deleted project reviews
  -> SecurityFinding rows (evidence span, rule, status=needs_review)
```

Analysis is repeatable: the unique `(review_id, finding_type)` constraint and service reconciliation prevent duplicate finding rows. If the source review changes, the match is refreshed and any prior human decision is cleared; if it stops matching or becomes deleted/spam/duplicate, the finding becomes `stale` and retains its historical evidence. Stale findings cannot be confirmed. Current findings remain observations until a permitted analyst marks them confirmed or dismissed; this confirms the text match, not an independently verified incident. Finding listing filters by the authorized project and organisation. The interface links each finding back to its review.

## Reports

```text
POST /api/v1/projects/{id}/reports
  -> report schema/authorization
  -> ReportService.generate_report
  -> gather_report_data from trusted existing analytics + scoped findings
  -> PDF (ReportLab) or Excel (OpenPyXL)
  -> configured StorageBackend
  -> Report metadata + audit events
  -> authenticated project-scoped download
```

The report now includes a bounded source appendix grouped by source/dataset, with eligible record counts, review-date range, collection-method description, origin ID, and sanitized source URL. The security report section includes finding type, severity, review identifier, source, safe source URL, retrieval/review dates, classification method, status, evidence, and nullable uncalibrated confidence. URL credentials, query strings, and fragments are omitted. A methodology appendix defines trust labels and states sampling, date, causal, and security limitations. Report content does not claim that phrase matches are confirmed incidents. Excel string cells beginning with spreadsheet formula markers are escaped as literal text.

## Existing analysis and workflow paths

- Sentiment routes call the existing sentiment service and configured engine (VADER by default); manual corrections remain service-owned.
- Topic routes call the existing deterministic TF-IDF/clustering service.
- Aspect routes call the existing aspect service.
- Trends, recommendations, alerts, comparison, and summaries use their existing service modules.
- Workflow start enters `workflow_service.start_workflow`, which persists a `running` workflow then calls the configured deterministic or LangGraph orchestrator synchronously. Each thin agent wrapper calls its existing trusted service. Step results are saved in `agent_workflows.result_summary`; approval is persisted and requires an authorized human. There is no separate durable background queue or per-step crash checkpoint.

## Existing direct collection boundary

All application collection is routed through `CollectionService`, which selects fixed collectors, applies source/project policy and bounds, and keeps SSRF validation. HTML collectors retain robots policy; the GitHub adapter calls only the official API under its public-repository access contract. It does not bypass authentication, CAPTCHAs, paywalls, or unsupported source policy. Existing Reddit OAuth-related collector behavior remains optional. There is no generic API catalog or arbitrary-source router.

## Evidence intelligence and duplicates

`Review.id` is the stable evidence ID. `evidence_service` retrieves eligible
reviews scoped to the authorized project and serializes stored provenance. The
`duplicate_detection_service` creates directional, idempotent links in
`review_duplicate_links` using provider identity, sanitized canonical URL, or
normalized exact text hash. It never merges or deletes review rows. Source
statistics retain origin record counts and separately report canonical evidence
and duplicate links.

`temporal_intelligence_service` compares dated eligible reviews in the current
window with the immediately preceding baseline. It uses phrase categories,
stored aspect results, negative sentiment, and review volume. It reports
windows, counts, rate changes, supporting review IDs, sources, and bounded
sample limitations. `root_cause_service` labels measured counts as facts,
temporal changes as observations, version overlap as correlation, and possible
explanations as hypotheses/recommendations; it does not infer causal truth.

Security analysis extends existing phrase reconciliation. The indicator
extractor parses URLs/domains, valid IPv4 values, CVE IDs, and SHA-256 strings as
`OBSERVED` only; query strings/fragments are removed and no reputation is
queried. Correlation groups repeated indicators across reviews and returns
observed patterns or possible incidents, never confirmed incidents.

## Persisted investigations

```text
POST /api/v1/projects/{id}/investigations
  -> authenticated project access + view_reviews
  -> investigation_service.create_investigation (QUEUED, idempotency key)
  -> PostgreSQL investigations row

flask --app run investigations-worker
  -> claim_next (conditional status/lease UPDATE)
  -> recheck requester membership, project and permission
  -> deterministic question-based plan or optional LLM JSON tool plan
  -> investigation_tools.execute_tool (fixed registry, validated arguments,
     server-derived project scope, permission check)
  -> existing analysis/evidence services
  -> bounded evidence collection
  -> optional structured synthesis + strict schema/status/evidence-ID validation
  -> deterministic evidence summary if provider absent or invalid
  -> persist activity, findings, result, review state and completion
```

The worker uses PostgreSQL leases and bounded attempts in a separate one-process
Compose service. It does not collect external sources. Tool activity stores
summaries/evidence IDs, not raw arguments or hidden model reasoning. Model
context redacts common email/phone patterns and explicitly labels external text
as untrusted. LLM findings can only be model interpretation, hypothesis, or
recommendation; they require retrieved evidence IDs and cannot set calibrated
confidence. Without a usable provider, deterministic summaries remain available
and semantic synthesis is explicitly unavailable. High-impact hypotheses,
recommendations, and security signals enter the human-review path.

Create/list/get and finding-review APIs are project scoped. Cancellation uses
an atomic state update for queued/waiting jobs only; a claimed worker job cannot
be cancelled while an LLM request is in flight and returns a conflict. The lazy
workspace is `/projects/:projectId/investigations`; the report system can include
a selected completed investigation through `investigationFindings`.

## Security boundaries

- Browser-supplied IDs are re-scoped by backend project/resource decorators.
- LLM report interpretation and bounded investigation synthesis remain optional and server-side; deterministic report metrics come from existing services.
- External review text remains untrusted analytical data. The new deterministic security phrase matcher does not execute instructions.
- Collector SSRF protections, redirect checks, response/time/page limits, and process-local collection serialization remain existing boundaries.
- No arbitrary SQL, shell, filesystem, or network tools exist. Evidence cannot grant authorization. No threat attribution, ATT&CK/STIX mapping, or external incident response is performed; only syntax-based indicator observations and deterministic correlation are implemented.
