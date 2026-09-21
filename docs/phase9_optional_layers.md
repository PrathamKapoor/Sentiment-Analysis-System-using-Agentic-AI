# Phase 9 — Optional LLM and Business-Context Layers

## What changed in Phase 9

Three additions, all **additive and opt-in**:

1. A pluggable **LLM interpretation layer** with a clean `LLMProvider`
   protocol, a `DeterministicProvider` always available, and an
   `OpenAICompatibleProvider` for any chat-completions endpoint.
2. An optional **business-context website** field on a project, with a
   bounded single-page extraction (the URL itself, not a crawl) reusing
   the existing SSRF protections.
3. A **report mode** field (`standard` / `enhanced`) on `Report`, with
   enhanced mode including a clearly-labelled "AI-Generated Contextual
   Interpretation" section.

The deterministic core, RBAC, multi-tenant safety, audit trail, and
human-approval gate are unchanged. The product works fully without the
two optional layers.

## Architecture

```
                             +-----------------------------+
                             |      user / dashboard       |
                             +--------------+--------------+
                                            |
                                            v
+-------------------+        +-----------------------------+
|   trusted         |        |   report_service.create    |
|   services:       |        |                             |
|   sentiment       | -----> |  gather_report_data(...)    |  deterministic
|   aspect          |        |  (project, sections, ...)   |  re-runnable
|   topic           |        +--------------+--------------+
|   keyword         |                       |
|   trend           |                       v
|   dataset profile |        +-----------------------------+
+-------------------+        |   sections_data dict        |
                             |   (measured numbers only)  |
                             +--------------+--------------+
                                            |
                  if mode == "enhanced":   |
                                            v
                             +-----------------------------+
                             |   llm_service.interpret     |
                             |                             |
                             |   build_analytics_for_llm() |  aggregate only
                             |   build_prompt()            |  rules + data
                             |   provider.complete()       |  HTTP, timeouts
                             |   -> LLMResult              |  or deterministic
                             |      text, provider,        |  fallback on any
                             |      model, status          |  failure
                             +--------------+--------------+
                                            |
                                            v
                             +-----------------------------+
                             |   sections_data             |
                             |   ["aiInterpretation"] =    |
                             |   {text, source, provider,  |
                             |    model, status, latencyMs, |
                             |    warning}                 |
                             +--------------+--------------+
                                            |
                                            v
                             +-----------------------------+
                             |   PDF / Excel renderer      |
                             |                             |
                             |   every measured section    |
                             |   -> same numbers as the    |
                             |      corresponding analysis|
                             |       page                  |
                             |                             |
                             |   AI section                |
                             |   -> labelled clearly       |
                             |   -> "not a measured        |
                             |      finding" notice        |
                             +-----------------------------+
```

## Deterministic / AI separation

This is a non-negotiable architectural principle. Concretely:

- The LLM is **only** invoked by `report_service.create_report`, and
  only when `mode == "enhanced"`.
- The LLM is **never** invoked by:
  - sentiment analysis, aspect analysis, topic analysis, keyword analysis
  - dataset profiling
  - collection (preview, test-connection, collect)
  - workflow steps
  - alerts, recommendations, AI summary draft generation
- The analytics dict that reaches the LLM is built from already-stored
  data; it contains aggregate numbers (counts, percentages, top topics,
  top keywords, top aspects, dataset-quality flag counts, trend
  direction). It does **not** contain raw review text, per-review rows,
  or any user-identifying detail.
- The prompt builder enforces a system prompt with explicit rules
  ("Do not invent numbers", "If the provided deterministic evidence does
  not support a claim, do not make that claim"). The user prompt is
  structured into a `TASK` block, a `VERIFIED DATA` block, and an
  optional `BUSINESS CONTEXT` block. Long lists are truncated with a
  `(+N more)` marker so a caller that accidentally passes review text
  cannot leak a full corpus.
- The report renderer labels the AI section in two ways: by source
  (`AI-Generated Contextual Interpretation (LLM)` vs
  `(Deterministic Fallback)`) and with an italicised "this section is
  generated, not a measured finding" notice. The same labelling appears
  in the Excel sheet and in the report row's `generationParameters`.

## LLM provider layer

`backend/app/services/llm/` contains:

- `provider.py` — the `LLMProvider` Protocol, the `LLMResult` dataclass,
  the `DeterministicProvider`, the `OpenAICompatibleProvider`, the
  `StubProvider` (test-only), the `get_provider()` factory with a
  per-process cache, `reset_provider_cache()` for tests, and
  `provider_status()` for the UI badge.

- `prompt_builder.py` — the `build_prompt(analytics, business_context)`
  function that returns `(system, user)` prompt strings. The system
  prompt is the immutable rule set. The user prompt contains the
  structured `VERIFIED DATA` and `BUSINESS CONTEXT` blocks, each with
  bounded sizes.

- `fallback_interpretation.py` — the `generate_deterministic_interpretation`
  function that produces a short, conservative, three-section text
  ("Key signals", "What the data suggests", "Limitations to be aware
  of") from the analytics dict alone. The output is clearly labelled
  as a deterministic interpretation (footer text).

- `__init__.py` — the public surface used by callers.

The provider contract maps every failure mode to a stable
`status` string (`ok | unavailable | timeout | http_error | malformed
| exception`). Callers branch on `result["source"]` (`"llm"` or
`"deterministic"`), never on exception types.

## Website context layer

`backend/app/services/website_context_service.py` exposes:

- `validate_url(url)` — shape-only check (scheme is http/https, host is
  present). The full SSRF check (DNS resolution + IP-range + connect-time
  rebinding) happens at extraction time.

- `extract_website_context(url, max_bytes=...)` — fetches the URL
  under the existing `SCRAPER_REQUEST_TIMEOUT_SECONDS`,
  `SCRAPER_MAX_RESPONSE_MB`, and `SCRAPER_USER_AGENT` settings, using
  the existing `ssrf_safe_connections()` context manager from
  `app.services.collectors.security`. The response is streamed and
  rejected if it exceeds the cap. Only the structured extraction
  (title, meta description, headings, body excerpt, content hash) is
  returned — raw HTML is never persisted.

- The status taxonomy: `ok | blocked | fetch_failed | parse_failed |
  too_large`. `blocked` is set when the existing SSRF guard rejects
  the URL (private/loopback/link-local IP, invalid scheme, unresolvable
  host). `fetch_failed` covers timeouts and HTTP errors. `parse_failed`
  covers non-HTML responses. `too_large` covers the response-size cap.

- `backend/app/services/project_website_service.py` provides the
  project-scoped CRUD: `set_website_url(project, actor, url,
  auto_refresh)`, `refresh_website_context(project, actor)`, and
  `get_website_context(project)`. Setting `websiteUrl` to `None` or
  `""` clears the URL and deletes the cached context row.

- `backend/app/models/project_website_context.py` is the
  `ProjectWebsiteContext` model with a unique constraint on
  `project_id` (one row per project). The cache is overwritten in
  place when the project owner re-runs extraction.

- `backend/app/routes/project_website.py` exposes
  `GET /api/v1/projects/{id}/website/context`,
  `PUT /api/v1/projects/{id}/website/context`, and
  `POST /api/v1/projects/{id}/website/context/refresh`. All routes
  are wrapped in `project_access_required` (404 on cross-tenant
  access, not 403). `PUT` and `POST` are gated on `edit_project`.

- `backend/app/routes/llm.py` exposes `GET /api/v1/llm/status`. The
  response is a small, safe summary of the active provider; no API
  key material, no full base URL.

## Report mode

`backend/app/services/report_data_service.py` adds a new section key
`aiInterpretation` to `ALL_SECTIONS`. `gather_report_data(...)`
accepts a new `ai_interpretation` parameter; when present, the section
is included with the LLM/deterministic metadata, source, model, status,
latency, and warning.

`backend/app/services/report_service.create_report` handles the
section-selection logic:

- `mode == "enhanced"`: the `aiInterpretation` section is always
  included, even if the caller did not list it. The deterministic
  sections are gathered first, then `_build_analytics_for_llm(project,
  sections_data)` produces the analytics dict, then
  `_build_business_context(project)` returns the cached website
  extraction (or `None`), then `llm_service.interpret_analytics(...)` is
  called. The result is re-gathered into `sections_data`.

- `mode == "standard"`: any `aiInterpretation` in the caller's
  requested sections list is removed. The LLM is never invoked.

The PDF and Excel renderers add a new section when `aiInterpretation`
is present in `sections_data`:

- PDF: a new heading ("AI-Generated Contextual Interpretation (LLM)"
  or "(Deterministic Fallback)"), an italicised "not a measured
  finding" notice, the interpretation text, and a small metadata
  line (source, model, status, latency, warning).

- Excel: a new "AI Interpretation" worksheet with the same fields
  plus the notice.

The report row's `generationParameters` JSON now includes
`{"mode": "...", "aiInterpretation": {"source": "...", "provider":
"...", ...}}` so the metadata is persisted alongside the report for
audit and reproducibility.

## Observability

`backend/app/services/observability.py` adds three small helpers:

- `get_or_create_request_id()` — reads `X-Request-ID` from the
  request, or generates a new UUID. Stored on `flask.g` for the
  request's lifetime.

- `step_timer(name, metadata=...)` — context manager that yields a
  dict and populates `startedAt`, `finishedAt`, `durationMs`, `name`,
  and `metadata`.

- `structured_log(logger, message, level=..., actor_user_id=...,
  project_id=..., organisation_id=..., **fields)` — thin convenience
  over `app.logger` that prefixes the log line with the request id,
  actor, project, and org ids, plus any extra fields (each value
  truncated to 200 chars).

`backend/app/__init__.py` registers `before_request` and
`after_request` hooks to set the request id and emit it on the
response (`X-Request-ID` header). Every API response now carries the
request id, and every audit log entry can be correlated to a
specific HTTP request.

## Pluggable sentiment engine

`backend/app/services/sentiment_analyzer.py` adds a `StubLexiconSentimentAnalyzer`
that uses a small hand-curated starter lexicon. Selection is
env-driven (`SENTIMENT_ENGINE=vader|stub`). The default remains VADER.
The new engine is documented as a demonstration that the
`SentimentAnalyzer` interface is pluggable — NOT as a production
replacement for VADER. Tests use it to verify the factory and the
shared result shape.

## Aspect analyser: transparency fields (Phase 10 audit)

An earlier draft shipped a small negation-hint post-correction on top
of VADER. Phase 10 audit found the flip produced false positives on
constructions like "The battery never fails.", where VADER's own
negation handling is already correct. The heuristic was removed.

What remains are the transparency fields on the per-aspect result:

- `compound` (the local-context VADER compound score)
- `evidence_text` (truncated to 300 chars, with a `[truncated]` marker
  on overflow)

Negation handling is VADER's responsibility and VADER's alone. The
module docstring documents this explicitly.

## Security review

The Phase 9 additions were reviewed for:

- **Tenant isolation.** All new routes use `project_access_required`
  or `jwt_required_custom`; cross-tenant access returns 404, not 403.
- **SSRF.** Website extraction reuses `validate_url_shape`,
  `validate_url_ssrf`, and `ssrf_safe_connections` from the existing
  collector security module. Same blocklist, same connection-time
  rebinding check, same process-level serialization.
- **Secret handling.** LLM API keys are read from environment only;
  `provider_status()` returns the active provider name, the model
  name, the host, and a `configured` boolean — never the API key,
  never the full base URL, never the timeout. The status endpoint is
  safe to expose to any authenticated user.
- **Prompt injection.** Review text is never sent to the LLM. The
  prompt builder caps list-shaped values to 5 items + a `(+N more)`
  marker, so a caller that accidentally passes review text cannot
  leak a full corpus. The system prompt explicitly forbids inventing
  numbers, claiming causation, and quoting review text verbatim.
- **Audit.** Every LLM call is best-effort audit-logged with
  provider, model, source, status, latency. When the caller does
  not supply an authenticated user/org (e.g. background tasks, tests)
  the audit row is silently skipped — the LLM call still completes.
- **Path traversal.** Report download paths are still server-controlled
  UUIDs; the report `mode` is server-validated against the
  `REPORT_MODES` enum.

## Limitations

- The LLM is treated as an external dependency. Its availability,
  latency, and cost are the operator's responsibility. The
  deterministic fallback is always available, but the *quality* of
  the interpretation section is bounded by the upstream provider.
- The website extraction is a single bounded page read. It is not a
  crawler, not a search-engine, and not a screenshot service. Pages
  with heavy JavaScript-rendered content will produce a sparse
  extraction (title + headings only).
- The negation-hint post-correction is conservative. It does not
  handle clause-level conjunctions ("but", "however") within a single
  sentence. The clause-level split is a documented baseline
  limitation.
- The benchmark remains a 62-row synthetic controlled diagnostic,
  not universal validation. The benchmark panel and report do not
  claim universal accuracy.

## What we did not change

- The deterministic core, RBAC, multi-tenant safety, audit trail,
  and human-approval gate are unchanged.
- The VADER default sentiment engine is unchanged.
- The aspect analyzer's 13-aspect seed dictionary is unchanged.
- The dataset profiler is unchanged.
- The collection layer is unchanged.
- The orchestrator's fixed step order is unchanged.
- The agentic workflow state machine is unchanged.
- The existing 291-test baseline (now 344 with Phase 9) is preserved.

## Deployment-oriented surfaces

These surfaces are tested by automated tests and are safe to ship
in a deployment-oriented prototype:

- The deterministic analytics core — exercised by the full
  backend test suite.
- The multi-tenant safety guarantees — verified by the cross-tenant
  tests in `test_aspect_vocabulary.py`, `test_workflows.py`,
  `test_website_context.py`, `test_report_modes.py`.
- The audit trail and human-approval gate — verified by
  `test_workflows.py` and seeded by `seed_service.py`.
- The report generation pipeline — verified by `test_report_modes.py` and
  `test_reports.py`; file paths are server-controlled, filenames are
  sanitized, and downloads are auth-gated.
- The website context extraction — verified against localhost, private
  IP, link-local, IPv6 loopback, oversized responses, malformed content
  types, and timeout behaviour by `test_website_security.py`. SSRF
  protections come from the same security module that guards collection.

## Not yet production-proven

- Real-world LLM provider quality. The provider interface has been
  tested against a mock, not against a live model on representative
  data. A small number of trial runs is necessary before enhanced
  reports can be trusted for a customer-facing report.
- Sustained concurrent report generation. Reports currently run
  synchronously inside the request handler — a slow LLM will block
  the caller. That is acceptable at this scale but is a documented
  limitation, not a capacity claim.
- Website-extraction quality across a broad set of real business
  sites. The extractor is conservative by design; some genuinely
  useful context will be missed and only a few sites have been
  inspected for extraction quality.

## What is not yet production-proven

- Real-LLM evaluation of the interpretation section's quality across
  domains. The fallback is the safe default; an operator who turns
  the LLM on should review a handful of generated reports to confirm
  the provider and model produce useful interpretations for their
  data.
- Long-running or multi-tenant website extraction at scale. The
  extraction is process-serialized with the existing collection
  lock; concurrent extraction requests from different projects are
  not yet benchmarked.
- LLM provider failover. The current `OpenAICompatibleProvider` is
  single-endpoint. A future enhancement could add a list of
  providers with a retry policy.
