# Phase 6 Deferred Issues

Non-blocking issues found or deliberately deferred during Phase 6 (web-data
collection). None of these break core functionality, expose data across
tenants, or represent a security gap in the default configuration — each is
isolated and documented per the deferred-resolution policy in the Phase 6
kickoff prompt.

---

### D6-01 — No persisted per-source selector configuration

**Module:** `app/services/collectors/static_html.py`

**Issue:** The Phase 6 brief describes a generic HTML collector supporting
configurable selectors (`review_container_selector`, `review_text_selector`,
etc.) per source. The approved `data_sources` schema (exactly `id,
project_id, type, url, keywords, enabled, last_collected_at, created_at`)
has no column to persist them.

**Current implementation:** Selectors can be supplied per-call as a
transient `selectors` object in the `POST /sources/{id}/preview` and
`POST /sources/{id}/collect` request bodies (validated by
`app/schemas/collection_schemas.py::SelectorOverrideSchema` as plain CSS
strings — never executable code). They are used for that one call only and
never saved. Without an override, two built-in heuristic selector sets
(schema.org microdata, then common `.review`/`.comment` class patterns) are
tried in order.

**Reason for temporary decision:** Adding a `collection_config` JSONB column
would be a schema amendment; per the project's established discipline
(same as every prior phase), that's only justified once a real, repeated
need is demonstrated — a one-off transient override already covers the
"selectors are data" requirement without touching the schema.

**Files affected:** `app/services/collectors/static_html.py`,
`app/schemas/collection_schemas.py`.

**Recommended future fix:** If real-world sources need the same selector
override on every collection run (not just once), add a nullable
`collection_config` JSONB column to `data_sources` via a new migration, and
have `StaticHTMLCollector` read a saved override before falling back to the
per-call one, then the built-in heuristics.

**Severity:** Low. **Migration eventually required:** Only if persisted
overrides become a real requirement.

---

### D6-02 — Reddit collection unavailable without API credentials

**Module:** `app/services/collectors/reddit_collector.py`

**Issue:** Reddit's terms require the official API (OAuth) for programmatic
access — this system does not and will not scrape reddit.com HTML directly.

**Current implementation:** `PublicRedditCollector.health_check()` and
`validate_source()` always report unavailable (`COLLECTION_UNSUPPORTED_SOURCE`)
without `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` configured, and even with
credentials present, the actual OAuth API integration itself isn't
implemented in Phase 6 (config plumbing exists; the API client doesn't).
This degrades gracefully — it does not block any other Phase 6 work, per
the "do not block all Phase 6 work" instruction.

**Reason for temporary decision:** No Reddit API credentials are available
in this environment, and implementing a full OAuth client-credentials flow
plus the Reddit listing API is out of scope for "build the data collection
capability" when zero other source types need OAuth.

**Files affected:** `app/services/collectors/reddit_collector.py`,
`app/services/collectors/registry.py`.

**Recommended future fix:** Implement `PublicRedditCollector` for real once
credentials are available: client-credentials OAuth token fetch, `GET
/r/{subreddit}/comments` or similar via `oauth.reddit.com`, normalize into
the same record shape every other collector already produces.

**Severity:** Low (source type was always going to need special-casing —
this is documented unavailability, not a bug). **Migration required:** No.

---

### D6-03 — No persisted manual policy override

**Module:** `app/services/collection_service.py::_policy_for`

**Issue:** The Phase 6 brief describes source policy metadata
(`allowed`/`blocked`/`requires_review`/`api_preferred`/`manual_upload_only`)
as something a source can be configured with.

**Current implementation:** Policy is computed fresh on every
preview/collect/status call — never persisted (same schema constraint as
D6-01: no column exists for it). It's `api_preferred` for `reddit`-type
sources without credentials, `blocked` when robots.txt disallows the target
path for our user agent, `allowed` otherwise. There is currently no way for
an org admin to force a source to `requires_review` or `manual_upload_only`
regardless of what robots.txt says.

**Reason for temporary decision:** Same schema-discipline reasoning as
D6-01 — the computed policy already satisfies "must not claim every public
URL is scrapable" without a schema change; a manual override is a
genuinely separate feature, not required for Phase 6 to be complete.

**Files affected:** `app/services/collection_service.py`.

**Recommended future fix:** Bundle with D6-01's `collection_config` column
if/when it's added — a `policyOverride` key alongside selector config.

**Severity:** Low. **Migration eventually required:** Only alongside D6-01.

---

### D6-04 — Scheduling deferred

**Module:** N/A — no scheduler exists.

**Issue:** The Phase 6 brief allows (but doesn't require) basic scheduling
support.

**Current implementation:** Manual collection only —
`POST /sources/{id}/collect` and the bulk
`POST /projects/{id}/sources/collect-enabled` are both user-triggered.
No Celery/Redis/cron was introduced.

**Reason:** Manual collection completed; persistent scheduler deferred to
Agentic orchestration/future infrastructure — introducing a task queue
purely to support "collect every N hours" would be disproportionate to
Phase 6's actual scope, and nothing in the existing architecture (Phases
1-5, all synchronous-within-request) needs one yet either.

**Files affected:** None.

**Recommended future fix:** When Phase 7's orchestration layer needs
recurring collection, evaluate APScheduler (lighter than Celery+Redis, no
new infra) before reaching for a full task queue.

**Severity:** Low. **Migration required:** No.

---

### D6-05 — `SCRAPER_ALLOW_PRIVATE_TARGETS` is a live security-relevant flag

**Module:** `app/services/collectors/security.py`, `app/config.py`

**Issue:** A dev-only config flag (`SCRAPER_ALLOW_PRIVATE_TARGETS`, default
`false`) exists to disable the localhost/private-IP SSRF block, added so
this phase's own manual acceptance testing could point a source at a
locally-run mock HTTP server without weakening SSRF protection for anyone
who hasn't explicitly opted in. Any config flag that can disable a security
control is worth flagging even when it defaults off.

**Current implementation:** Checked via `current_app.config` on every
`validate_url_ssrf`/`validate_url_shape` call; defaults false in every
`config_by_name` entry (`BaseConfig` doesn't set it true, and no
environment sets `SCRAPER_ALLOW_PRIVATE_TARGETS=true` by default).

**Reason for temporary decision:** Needed for real (non-mocked) manual
verification against a locally-controlled mock source, consistent with
"unless explicitly required for local development tests" in the Phase 6
brief's own SSRF section.

**Files affected:** `app/config.py`, `app/services/collectors/security.py`.

**Recommended future fix:** Before any real deployment, consider gating
this additionally behind `FLASK_ENV == "development"` (belt-and-suspenders
against a misconfigured production `.env`), or removing it entirely once
CI has a proper mock-server fixture and no one needs to run this manually
against `127.0.0.1` again.

**Severity:** Medium (security-relevant, but off by default and documented
loudly here and in the README). **Migration required:** No.

---

### D6-06 — robots.txt policy check is best-effort, not a legal guarantee

**Module:** `app/services/collectors/robots.py`

**Issue:** If robots.txt is unreachable, missing, or fails to parse, the
policy check treats the source as `allowed` by default (most sites have no
robots.txt and mean nothing by its absence).

**Current implementation:** `is_collection_allowed_by_robots()` returns
`(True, checked=False)` on any fetch/parse failure — never blocks on
ambiguity, only on an explicit `Disallow` match.

**Reason:** A hard fail-closed policy (block collection whenever robots.txt
can't be fetched) would make collection unusable against any source with
transient network issues, for no real compliance benefit — robots.txt
absence has never meant "scraping forbidden."

**Files affected:** `app/services/collectors/robots.py`.

**Recommended future fix:** None required — documented, not a bug. Worth
restating in the README (see "Compliance" section) so no one mistakes
"robots.txt allowed it" for "this is definitely legal to scrape."

**Severity:** Low (documentation clarity, not a functional gap). **Migration
required:** No.

---

### D6-07 — Pagination "next page" detection is heuristic

**Module:** `app/services/collectors/static_html.py::_find_next_page`

**Issue:** Multi-page collection looks for `a[rel='next']`, `a.next`, or
`a.pagination-next` to find the next page. Sites using other pagination
markup (numbered page links only, JS-driven "load more", cursor-based
infinite scroll) won't be followed past page 1.

**Current implementation:** Single-page collection still works correctly
for these sites (`recordsFound` reflects only page 1, `truncated` stays
`false` since no error occurred — it just means pagination silently stops,
which is arguably correct behavior for an unsupported pagination style
rather than an error).

**Reason:** JS-driven pagination is explicitly out of scope (no
Playwright/Selenium without genuine need — see README), and adding more
pagination-link heuristics without a real target site to validate against
risks guessing wrong.

**Files affected:** `app/services/collectors/static_html.py`.

**Recommended future fix:** Expand the heuristic list if/when a real target
site's pagination markup is known, or accept an explicit `nextPageSelector`
alongside the other per-call selector overrides (D6-01's pattern).

**Severity:** Low. **Migration required:** No.
