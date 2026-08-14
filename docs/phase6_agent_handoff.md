# Phase 6 → Phase 7 Agent Handoff

This document describes the **actual** Phase 6 data-collection implementation
as it exists today — not an aspirational design. It's written for whatever
builds the Phase 7 Data Collection Agent (or any other orchestration code)
on top of it. Written during a limited retrospective verification pass
before Phase 7 begins; no redesign was performed — see
`docs/phase6_deferred_issues.md` and `docs/phase6_schema_changes.md` for the
original Phase 6 design record this builds on.

---

## 1. CollectionService entry points intended for agents

`app/services/collection_service.py` is the **only** module Phase 7 should
call into for collection. Every function takes plain Python values (a
`DataSource` ORM instance, a user ID, plain dicts/strings) — none of them
take or need a Flask `request` object. They do read `current_app.config`
(via `flask.current_app`), so callers need an **active Flask application
context** (`with app.app_context():`), not a request context. This is the
same contract every other service module in this codebase already has.

| Function | Purpose | Raises on hard failure |
|---|---|---|
| `test_connection(source, actor_user_id)` | Cheap reachability probe | Never — always returns `{"available": bool, "message": str}` |
| `preview_source(source, actor_user_id, options=None)` | Sample records, no DB writes | `CollectionError` |
| `collect_source(source, actor_user_id, trigger_type="manual", options=None)` | Full collection + ingestion | `CollectionError` |
| `collect_enabled_sources_for_project(project_id, actor_user_id)` | Bulk collect across a project's enabled sources | Never — per-source failures are caught and returned in the results list, not raised |
| `get_collection_status(source)` | Current state (derived, read-only) | Never |
| `get_collection_history(source, limit=20)` | Recent activity (derived, read-only) | Never |
| `get_collector_capabilities()` | Static per-source-type capability info | Never |

`trigger_type` is a free-form string recorded in the audit log metadata
(`"manual"`, `"bulk"` are used today) — Phase 7 can pass e.g. `"agent"` to
distinguish agent-triggered runs in the audit trail without any code change.

**Do not instantiate or call a collector class directly.** See §4.

## 2. Collector registry usage

`app/services/collectors/registry.py`:
- `get_collector(source_type, limits) -> BaseCollector | None` — used
  internally by `collection_service`. A `limits` (`CollectionLimits`)
  instance must be built from config first (see `collection_service._limits()`
  for the exact fields).
- `describe_source_type(source_type) -> dict` / `describe_all_source_types() -> list[dict]`
  — the capability-discovery entry point (§6). Exposed at the service layer
  as `collection_service.get_collector_capabilities()`.

Collectors are stateless-per-call adapters keyed by `DataSource.type`, not
one per literal source type — `StaticHTMLCollector` covers
`review_site`/`ecommerce`/`forum`/`blog`/`news`/`survey`; `PublicRedditCollector`
covers `reddit`. Neither collector class imports `flask.request` or `flask.g`
— confirmed by inspection during this retrospective. `security.py` imports
`flask.current_app` only (application context, not request context).

## 3. Permission required

No new permission codes exist for collection (none were added in Phase 6,
none were added in this retrospective). Reused exactly:
- `manage_data_sources` — test-connection, preview, collect, collect-enabled
  (every state-changing collection action)
- `view_reviews` — collection-status, collection-history (read-only)

If Phase 7 adds an agent identity distinct from a human user, it must still
resolve to an `actor_user_id` that holds one of these permissions in the
target organisation — `permission_service.has_permission()` is the existing
check, unchanged.

## 4. Tenant-validation contract

Every HTTP route enforces tenant isolation via `data_source_access_required`
/ `project_access_required` (`app/decorators/auth.py`) **before**
`collection_service` is ever called — a source ID from another organisation
404s at the decorator, the service function never even sees it.

**If Phase 7 calls `collection_service` directly (not through HTTP), it is
responsible for loading the `DataSource` and verifying organisation
membership itself first** — `collection_service` functions trust that the
`source` object passed in already belongs to a project the caller is
authorized to act on. They do not re-check tenant ownership internally
(same pattern as every other `*_service.py` module in this codebase, e.g.
`report_service.py`, `alert_service.py` — the access decorator is always
the enforcement point, not the service).

## 5. Policy enforcement contract

`_policy_for()` (robots.txt check + Reddit-availability check) lives **only**
in `collection_service.py`, called before `collector.validate_source()` and
before `collector.collect()`/`collector.preview()`. **Collectors themselves
do not check policy** — `StaticHTMLCollector.collect()` will happily fetch
whatever URL it's given if called directly, with no robots.txt check.

**This means: Phase 7's Data Collection Agent must call
`collection_service.collect_source()` / `preview_source()` — never a
collector class directly — or it will bypass `COLLECTION_NOT_PERMITTED`
policy enforcement entirely.** This was verified during this retrospective
by tracing every call site; no code change was needed because the existing
route layer already only ever goes through `collection_service` (§1) — the
risk is specifically an agent instantiating `StaticHTMLCollector` itself,
which nothing currently prevents at the Python level. Treat "always go
through CollectionService" as a hard rule for any new caller.

## 6. SSRF contract

`app/services/collectors/security.py`:
- `validate_url_shape(url)` — format-only (scheme, host present, rejects
  `file://`/`javascript:`/literal `localhost`). No network call.
- `validate_url_ssrf(url)` — resolves DNS via `socket.getaddrinfo` and
  rejects any resolved address that is private/loopback/link-local/
  reserved/multicast/unspecified (covers IPv4 RFC1918 + loopback +
  link-local, and IPv6 loopback/ULA/link-local via Python's `ipaddress`
  module). Called before every fetch and again on every redirect hop — a
  public URL that redirects to a private IP is blocked at the redirect.
- `ssrf_safe_connections()` — a context manager added during this
  retrospective that closes the residual DNS-rebinding gap: it hooks
  `urllib3.util.connection.create_connection` (the actual connect
  entrypoint `requests`/`urllib3` use) so the **literal address being
  connected to** is re-validated at connect time, not just at the earlier
  `validate_url_ssrf()` call. Every real HTTP call in `static_html.py` and
  `robots.py` is wrapped in this context manager. See §"SSRF / DNS safety
  result" in the retrospective completion notes for why this was needed and
  what it does and doesn't cover.

`SCRAPER_ALLOW_PRIVATE_TARGETS` (default `false`) can disable the
private-IP checks — environment-variable-only, no API/schema/frontend/
collector-option surface exposes it (verified by grep during this
retrospective — zero references outside `config.py` and `security.py`).
**Must never be set true anywhere reachable from the internet, and must
never become an agent-controllable parameter.**

## 7. Duplicate semantics

**Duplicate detection does not mean duplicate rows are absent.** Collected
(and uploaded-dataset) reviews that match an existing review's normalized
text hash within the same project are still **inserted**, flagged
`is_duplicate: true` — never rejected, never deleted. This is the same
behavior dataset ingestion has had since Phase 2; Phase 6 collection reuses
the identical `text_cleaning.normalize_for_dedup()` helper and the same
project-scoped comparison query.

There is **no `duplicate_of` (or equivalent) linkage column** — `reviews`
only has the boolean `is_duplicate` flag, nothing pointing back at which
review it duplicates. Do not assume such a linkage exists; it would require
a schema amendment that was not made in Phase 6 or this retrospective.

Analysis services exclude duplicates **by default**, not by their absence:
`sentiment_service.eligible_reviews_query(project_id, include_duplicates=False)`
filters `Review.is_duplicate.is_(False)` unless the caller opts in. Phase 7
Data Quality/Sentiment/Topic/Aspect agents must respect this existing
opt-in pattern — calling the eligible-reviews path with
`include_duplicates=True` will include flagged duplicates in analysis, so
don't do that unintentionally.

## 8. Synchronous execution behavior

Collection is **fully synchronous within one function call** — no
background job, no polling, no `collection_jobs` table. `collect_source()`
runs the whole flow (policy check → health check → fetch/paginate →
normalize → validate → dedup → insert → audit) and returns a complete
result before returning control to the caller. This matches every other
"run something and get a result" operation in this codebase (dataset
validate/process since Phase 2, every analysis run since Phase 3).

Upper-bound behavior, all configurable via env vars (`app/config.py`),
defaults shown:

| Limit | Default | Effect |
|---|---|---|
| `SCRAPER_MAX_PAGES` | 10 | Hard cap on pages followed in one `collect()` call |
| `SCRAPER_MAX_RECORDS` | 500 | Hard cap on records collected in one call |
| `SCRAPER_REQUEST_TIMEOUT_SECONDS` | 15 | Per-HTTP-request timeout |
| `SCRAPER_MAX_RETRIES` | 2 | Max retries per HTTP request (timeout / 429-with-Retry-After / transient 5xx only) |
| `SCRAPER_REQUEST_DELAY_SECONDS` | 1 | Delay between successive page fetches and between retries |
| `SCRAPER_MAX_REDIRECTS` | 5 | Max redirect hops per page fetch |
| `SCRAPER_MAX_RESPONSE_MB` | 5 | Hard cap on a single HTTP response body |

**Worst-case wall-clock for one `collect_source()` call**, roughly:
`SCRAPER_MAX_PAGES × (SCRAPER_MAX_RETRIES + 1) × SCRAPER_REQUEST_TIMEOUT_SECONDS`
plus retry/inter-page delays — with defaults, a worst-case pathological
source (every page timing out, every retry exhausted) is bounded at
roughly `10 × 3 × 15 = 450` seconds. A well-behaved source completes in a
few seconds. **Phase 7 should orchestrate this existing synchronous service
directly (e.g. call it from within an agent's own step/tool-call), not
introduce a task queue "to be safe" — scheduling remains explicitly
deferred (D6-04); if a real timeout concern emerges in practice, wrap the
call with a caller-side timeout rather than changing this service's own
execution model.**

## 9. Error taxonomy

`CollectionError` (`app/errors/exceptions.py`) carries a stable `.code`
from this fixed set:

```
COLLECTION_INVALID_URL          COLLECTION_SSRF_BLOCKED
COLLECTION_SOURCE_DISABLED      COLLECTION_NOT_PERMITTED
COLLECTION_TIMEOUT              COLLECTION_RATE_LIMITED
COLLECTION_HTTP_ERROR           COLLECTION_PARSE_ERROR
COLLECTION_UNSUPPORTED_SOURCE   COLLECTION_RESPONSE_TOO_LARGE
```

`.message` is always a safe, user/agent-facing string — raw exceptions and
stack tracebacks are never attached to it and never propagate out of
`collection_service` functions as anything other than this typed error.

**Hard stop vs. warning/partial success — these are structurally distinct,
not just different string values:**
- **Hard stop** = `CollectionError` raised. Nothing was collected/inserted
  this call (or the operation was refused before starting, e.g. disabled
  source / policy block). Catch `CollectionError`, read `.code`/`.message`.
- **Warning / partial success** = `collect_source()` returns normally with
  a summary dict whose `status` field is one of `"completed"` /
  `"partial_success"` / `"no_records"`. `partial_success` means some
  records were found but some were invalid or the run was truncated by a
  limit (`truncated: true` in the summary); `no_records` means the fetch
  succeeded but nothing matched — both are **not exceptions** because
  "nothing new this run" and "some rows were skipped" are legitimate
  outcomes, not failures. Always check `status`/`truncated`/
  `recordsInvalid` on a successful return rather than assuming
  `status == "completed"`.

## 10. Collector availability behavior

`collection_service.get_collector_capabilities()` returns one entry per
registered source type:

```python
{
    "sourceType": "reddit",
    "collectorType": "reddit_api",
    "available": False,
    "unavailableReason": "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not configured.",
    "supportsPreview": False,
    "supportsPagination": False,
    "requiresCredentials": True,
}
```

Call this **before** attempting collection on a source whose type might be
unavailable. `available: false` should translate to "skip this source and
report a warning," never a crash — `PublicRedditCollector.collect()` itself
also never crashes on an unavailable state, it raises a normal
`CollectionError(code="COLLECTION_UNSUPPORTED_SOURCE")`, which is a
catchable, expected hard-stop per §9, not an unhandled exception.

## 11. Audit behavior

Every collection action writes to the existing `audit_logs` table
(`entity_type="data_source"`, `entity_id=<source id>`):
`data_source.test_connection`, `collection.preview`, `collection.started`,
`collection.completed`, `collection.failed`, `collection.blocked_by_policy`.
`metadata` holds structured counts/codes (`recordsFound`/`Inserted`/
`Duplicate`/`Invalid`, `errorCode`, `safeErrorMessage`, `triggerType`) —
**never raw scraped page content**.

`get_collection_status()`/`get_collection_history()` reconstruct current
state and history purely from these rows plus `data_sources.last_collected_at`
— verified during this retrospective to correctly use the composite index
added in migration `0006` (`entity_type, entity_id, timestamp`), confirmed
via `EXPLAIN`-equivalent reasoning over the exact filter/order pattern both
functions use. **No `collection_jobs` table exists or is needed for either
function** — Phase 7 can build on this directly. Only revisit that decision
if a real resumable/background workflow requirement appears (see
`docs/phase6_schema_changes.md`).

## 12. Features explicitly unavailable

- **Scheduler** — none. Manual/on-demand only (`collect_source`,
  `collect_enabled_sources_for_project`). No Celery/Redis/cron (D6-04).
- **Persisted selectors** — a caller may pass a transient `selectors`
  override for one `preview`/`collect` call; nothing is saved to the
  `data_sources` row (D6-01). No schema column exists for it.
- **Persisted policy override** — policy (`allowed`/`blocked`/
  `api_preferred`) is computed fresh on every call; there's no way to force
  a source to `requires_review`/`manual_upload_only` regardless of
  robots.txt (D6-03).
- **Reddit OAuth** — not implemented. `PublicRedditCollector` always
  reports itself unavailable (D6-02); this retrospective did not implement
  it, per explicit instruction.
- **Autonomous collection** — nothing in this codebase currently triggers
  collection without an explicit, permission-checked human (or
  human-authorized-agent) action. `collect_source`/`collect_enabled_sources_for_project`
  are always caller-invoked; there is no code path that runs collection on
  its own.
