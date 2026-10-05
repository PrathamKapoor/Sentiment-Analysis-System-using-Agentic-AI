# Customer and Cyber Intelligence Implementation Plan

> Execute each phase in order in this checkout. Do not commit, push, change Git author metadata, or add collaborators.

**Goal:** Evolve the existing multi-tenant sentiment application into a controlled customer and product intelligence platform with evidence-linked security findings, bounded external-source search, validated optional LLM investigations, human review, and a deployable managed-infrastructure path.

**Architecture:** Preserve the existing Flask service and React API boundaries. Add canonical product metadata and provenance records, register fixed-host source adapters behind `CollectionService`, keep deterministic analysis and authorization in trusted services, and treat LLM output as untrusted structured proposals. Extend durable workflow persistence only where resumable investigations require it. Keep all changes additive through new Alembic revisions and retain backwards-compatible API fields where practical.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Marshmallow, React/Vite, existing deterministic analytics, optional provider abstraction, PostgreSQL, Redis, S3-compatible storage, Vercel Functions for the SPA/API deployment path where compatible.

**Spec:** User-provided “MASTER IMPLEMENTATION PROMPT”, sections 2–41 received so far; incorporate later sections before closing implementation.

## Global Constraints

- PostgreSQL remains the production database; add migrations after `0009` and never rewrite accepted migrations.
- Preserve organization/project authorization, 404 tenant hiding, audit logging, and stable response envelopes.
- All source adapters remain fixed-host, bounded, policy-aware, SSRF-protected, and provenance-preserving.
- Never bypass authentication, robots restrictions, CAPTCHA, paywalls, or source API terms.
- External content and model output are untrusted data; LLM tools are explicitly allow-listed and argument-validated.
- Deterministic analytics, authorization, metrics, persistence, and security policy remain independent of LLM availability.
- Human approval remains mandatory for high-impact or uncertain findings and external publication.
- Do not add an autonomous scraper, SIEM, SOC, offensive security actions, or arbitrary model-controlled tool execution.
- Do not commit, push, change author identity, or add collaborators.

---

## Repository Areas and Ownership

| Area | Responsibility |
|---|---|
| `backend/app/models/`, `backend/migrations/versions/` | Product identity, normalized feedback provenance, security findings, investigation state and evidence relationships. |
| `backend/app/services/collectors/`, `collection_service.py`, `source_fallback.py` | Fixed-host source adapter registry, bounded search, policy results, keyword filtering, provenance, ingestion. |
| `backend/app/services/` | Deterministic classification, metrics, emerging themes, anomaly evidence, competitor/switching signals, security analysis, structured LLM boundary. |
| `backend/app/routes/`, `schemas/`, `decorators/` | Tenant-scoped validated API contracts and authorization. |
| `frontend/src/pages/`, `components/`, `services/` | Product/entity settings, source search/status, intelligence review, investigations, exports. |
| `backend/tests/` | Unit, route, migration, tenant-isolation, source-policy, prompt-injection, and workflow regressions. |
| `docs/`, `README.md`, deployment files | Reconcile docs with actual implementation and record provider/retention/deployment constraints. |

## Phase 1: Make the source abstraction and canonical entity real

1. Add a project-scoped canonical entity model/API with deterministic URL and text normalization, validated aliases, SKU/identifier fields, and custom/include/exclude/security/competitor keyword groups.
2. Keep `product_or_topic` as a backwards-compatible seed value; never let an LLM write canonical entity data without schema and business-rule validation.
3. Add normalized source-run outcomes and provenance links so multiple source observations can refer to one canonical feedback item without losing source identity or breaking current review consumers.
4. Make configured include/exclude/security/competitor/custom terms affect collection and analysis. Empty keyword groups preserve current behavior; include terms use any-match semantics; exclusion terms remove matching records before ingestion; security and competitor terms annotate/classify evidence without discarding unrelated records.
5. Add fixed-host, independently testable source adapters selected from an explicit user-configured set. Start with sources whose official APIs support the intended data and whose authentication/terms are configured; do not auto-execute metadata discovery candidates.
6. Test URL normalization, aliases, unknown/malformed entities, keyword matching, record filtering, duplicate provenance, provider failure states, limits, and compatibility with existing `Review` origin constraints.

## Phase 2: Deterministic customer and security intelligence

1. Add validated feedback categories and evidence-bearing security finding persistence, with tenant/project/review foreign keys, classification method, bounded evidence spans, severity, confidence, status, and timestamps.
2. Implement deterministic phrase/rule extraction for supported security categories, competitor mentions, switching intent, and journey-stage hints. Use `unknown` when evidence is insufficient.
3. Extract candidate IPs, domains, URLs, hashes, CVEs, and malware names only as unverified indicators attached to source evidence; never create an incident or CTI assertion solely from a token match.
4. Add source-denominated rates only when denominator and sampling context exist. Return numerator, denominator, period, source, and limitations; otherwise expose raw count only.
5. Add explainable time-window comparisons for emerging themes, complaint spikes, sentiment changes, and source shifts. Require minimum sample sizes and explicitly identify comparison periods and channel bias.
6. Keep root-cause output typed as observation, correlation, hypothesis, or supported explanation; do not claim causality from co-occurrence.
7. Expand recommendation evidence and prioritization only where supporting values can be calculated; leave unknown effort/impact/confidence unset instead of inventing scores.
8. Add route, migration, tenant-isolation, adversarial-text, and statistical edge-case tests before frontend exposure.

## Phase 3: Structured optional LLM and bounded investigator

1. Preserve `TextGenerationProvider`; make provider configuration explicit and provider-neutral, adding another vendor only when its response schema and error behavior are tested.
2. Define typed schemas for ambiguous classification, cluster naming, security finding proposals, investigation summaries, and recommendations. Reject malformed, overlong, unsupported-enum, invalid-span, cross-tenant, or evidence-free outputs.
3. Keep provider requests free of raw identifiers/secrets; document data sent and require explicit configuration for sending review content to an external provider. Respect source-specific terms before forwarding source content.
4. Add a fixed investigator tool registry for the requested read-only evidence functions. Each call must re-check current user membership, project/resource scope, permission, arguments, rate limit, output size, and audit policy.
5. Store investigation state, tool-call summaries, evidence references, and checkpoint progress in PostgreSQL before pause/resume. Add hard limits for tools, steps, external requests, duration, retries, page size, and tokens.
6. Treat retrieved content and tool output as untrusted content in prompts. Add integration tests proving prompt injection cannot invoke unauthorized tools, expose another tenant, skip approval, or exceed budgets.
7. Human-gate high-severity/low-confidence/conflicting findings and publication; approval must not trigger external actions implicitly.

## Phase 4: User workflows, investigation workspace, and exports

1. Add entity and keyword configuration to the existing project workspace, with sensible defaults and accessible validation/error states.
2. Add source selection, per-source capability/status/limits, progress, failure reasons, and per-source counts to the existing Data Source workflow.
3. Add security findings and investigation views with evidence links, source provenance, related reviews, analyst notes, status, confidence, approval state, and verified ATT&CK mappings.
4. Add source-bias and sampling context to comparisons and trends; distinguish observed clusters from confirmed incidents.
5. Extend PDF/Excel and machine-readable exports with sources, time ranges, method, limitations, denominators, evidence references, LLM involvement, and valid structured CTI only.
6. Validate STIX 2.1 output with a standards validator and only generate supported objects from evidence that meets deterministic business rules. ATT&CK IDs must come from a pinned/validated registry, not model output.
7. Run Vite build and browser/API walkthrough for each implemented flow.

## Phase 5: Managed deployment and Vercel compatibility

1. Decide and document whether Vercel hosts only the Vite frontend or both frontend and Flask API. Prefer separate projects if that preserves the current API service boundary.
2. If Flask runs as a Vercel Function, add an explicit WSGI entrypoint/config and verify Python/dependency bundle and function duration with the actual package set.
3. Replace local uploads/reports with configured durable object storage for serverless use; never rely on ephemeral local files. Exercise real object storage if credentials/environment are available, otherwise label mock-only verification.
4. Reconcile the 25 MiB upload contract with Vercel’s function request-body cap; use direct-to-object-storage upload or another verified transfer path rather than silently lowering the accepted file size.
5. Remove correctness reliance on process-local collection locks and in-memory revocation/rate state before enabling concurrent serverless instances; use shared coordination/state or keep Flask on a persistent managed container service.
6. Keep PostgreSQL migrations as an explicit one-shot deployment operation; set secrets only in deployment environment settings and provide a least-privilege environment checklist.
7. Validate deployment configuration/build locally; perform a live deploy only when credentials and explicit deployment authorization are available.

## Phase 6: Security, documentation, and final audit

1. Add deterministic attacks for injection, tool misuse, cross-tenant references, malformed structured output, data exfiltration attempts, context flooding, and budget exhaustion.
2. Verify all entity, source, feedback, finding, investigation, report, export, and file lookups use backend authorization.
3. Re-run migration audit on PostgreSQL and the complete backend suite; run frontend production build and browser walkthrough.
4. Run dependency/security scans available in CI; investigate new advisories rather than suppressing them.
5. Update README, AGENTS.md, API contracts, data-retention/privacy notes, source/LLM provider setup, deployment guides, and release verification to match implemented behavior.
6. Inspect final Git diff/status, ensure no secrets/artifacts/identity changes, and report exact test/deployment evidence and remaining blockers.

## Current Baseline Evidence

- Backend full suite before implementation: 434 passed, 1 failed, 2 warnings; the failure is `test_s3_backend_missing_boto3_raises`, whose assumption that boto3 is absent is invalid in the current environment. The test was made deterministic and its module passed 5/5.
- Frontend production build passed before implementation, with an existing Vite chunk-size warning (main JavaScript bundle about 564 kB).
- Existing production migrations end at `0009`; current schema has 25 application tables.
- Vercel officially supports Flask Functions, but its function request body limit is 4.5 MB; this conflicts with the app's current 25 MiB upload limit unless upload handling changes.
- Git checkout was clean before this task. Current implementation changes are listed in `docs/model_changes.md`; do not confuse this initial-state fact with current Git status.

## Execution Status (Updated 2026-10-04)

Implemented in this working tree: project entity metadata and deterministic resolver; validated keyword groups with controlled-collection filtering and upload annotations; deterministic evidence-linked security signals with analyst triage and stale-evidence reconciliation; PDF/Excel security findings, bounded source provenance, trust labels, and Excel formula-safety; frontend entity/security panels; Vite SPA hosting configuration; PostgreSQL migrations `0010`–`0013`; corresponding API/unit/integration regressions; and actual-flow/decision/handoff documentation.

Verification: the full backend suite passed 453 tests (0 failures, 2 existing warnings) after the source-fingerprint addition; the URL-credential rejection assertion passed separately. All 19 report tests passed. PostgreSQL migration upgrade/downgrade/re-upgrade through 0013 passed. Vite build passed with the documented large-chunk warning. No live browser walkthrough or Vercel deployment was performed.

Explicitly deferred: general multi-source search adapters, broad category classification, competitor/switching analysis, emerging themes and normalized statistical metrics, root-cause evidence graph, calibrated security scoring, indicator/CTI/ATT&CK/STIX extraction, LLM investigation tools, durable async execution, and live deployment/browser walkthrough. See `docs/customer_cyber_intelligence.md` for exact current boundaries. In-process threads were rejected as a substitute for durable execution because they do not resume after process restart and would not coordinate collection across replicas.
