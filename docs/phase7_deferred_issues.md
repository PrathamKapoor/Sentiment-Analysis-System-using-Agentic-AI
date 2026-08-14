# Phase 7 Deferred Issues

Non-blocking issues deliberately deferred during Phase 7 (agentic orchestration).
None of these expose data across tenants, allow an autonomous high-impact
action, or break existing functionality — each is isolated and documented
per the deferred-resolution policy in the Phase 7 kickoff prompt.

---

### PHASE7_DEFERRED_LANGGRAPH

**Component:** Orchestration engine (`app/services/agents/orchestrator.py`).

**Issue:** The Phase 7 brief allows (but doesn't require) using LangGraph
for workflow orchestration.

**Temporary behavior:** A custom, deterministic orchestrator was
implemented instead — plain Python control flow (a fixed step order, a
per-workflow-type default step selection, a small blocked-steps map for
critical-agent failure). No LangGraph dependency was added.

**Why:** This entire codebase is synchronous-within-one-HTTP-request
throughout every phase (no Celery, no Redis, no background workers, no
async job queue anywhere). LangGraph is designed around graph-based
stateful execution, typically paired with async/streaming and its own
state-persistence model — adopting it here would mean either building a
real async execution layer just to host it (disproportionate to Phase 7's
actual scope) or using it in a degraded synchronous mode that gains none of
its actual benefits while still adding a new dependency tree
(`langgraph`/`langchain-core` and their own pinned sub-dependencies) to a
project that has been deliberately minimal about dependencies across every
phase so far (Phase 6 chose `requests`+BeautifulSoup over Selenium/Scrapy
for the identical reason). The architectural objective — controlled,
auditable, testable agent orchestration with clear step boundaries — is
fully met by the custom orchestrator without that risk.

**Future solution:** If a future phase genuinely needs graph-based
branching/parallelism beyond a fixed step order (e.g. dynamic step
insertion based on intermediate results), reconsider LangGraph then, once
there's a concrete async execution story to host it in.

**Affected files:** `app/services/agents/orchestrator.py`,
`app/services/workflow_service.py`.

**Risk:** None — this is a technology choice, not a capability gap.
**Migration required:** No.

---

### PHASE7_DEFERRED_LLM_PROVIDER

**Component:** `app/services/agents/provider.py`.

**Issue:** The Phase 7 brief describes an AI/LLM provider abstraction with
multiple possible implementations (deterministic, local model, external).

**Temporary behavior:** `TextGenerationProvider` interface exists;
`DeterministicProvider` (wrapping the existing Phase 5 template-based
summary generator) is the only implementation. `get_provider()` always
returns it. No external API key is required or read anywhere in the
codebase.

**Why:** No LLM provider is configured in this environment, and per the
Phase 7 brief itself, "No external paid API should be mandatory" — the
system must work with `DeterministicProvider` alone, which it does. Adding
a real external-provider implementation with no credentials to actually
test it against would be speculative, unverifiable work.

**Future solution:** When a real provider is available, implement it
against the existing `TextGenerationProvider` interface and select it in
`get_provider()` based on config, falling back to `DeterministicProvider`
when `is_available()` is `False` — the interface was designed for this
from the start, no agent code would need to change.

**Affected files:** `app/services/agents/provider.py`.

**Risk:** None — deterministic summaries/recommendations already existed
as the sole implementation since Phase 5; nothing regressed.
**Migration required:** No.

---

### D7-01 — Workflow resume only re-attempts the report step

**Component:** `app/services/workflow_service.py::resume_workflow`.

**Issue:** A workflow that pauses at `waiting_for_approval` always does so
for the same reason today — the report step needed an approved summary
that didn't exist yet (see `report_agent.py`). `resume_workflow()` is
hard-coded to re-run only `ReportAgent`, not "whichever step was waiting."

**Temporary behavior:** This is correct for every case Phase 7 actually
produces (report is the only step with an approval gate), but the function
name implies more generality than the implementation has.

**Future solution:** If a future agent introduces its own approval gate
(e.g. a hypothetical "publish" step), generalize `resume_workflow` to
inspect which step is `waiting_for_approval` and dispatch to the matching
agent, rather than assuming it's always the report step.

**Affected files:** `app/services/workflow_service.py`.

**Risk:** Low — behavior is correct for every workflow type Phase 7
defines; only the abstraction is narrower than its name suggests.
**Migration required:** No.

---

### D7-02 — No true background execution; a workflow cannot be cancelled mid-run

**Component:** `app/services/workflow_service.py`, `app/routes/workflows.py`.

**Issue:** Every workflow runs fully synchronously within one HTTP request
— `POST /projects/{id}/workflows` doesn't return until every requested
step has finished (or the workflow paused for approval). There is no
"running in the background" state a user could cancel mid-flight; `cancel`
only works on a workflow already sitting in `waiting_for_approval`.

**Temporary behavior:** For a pathological worst case (many agents, a
Data Collection step hitting slow/failing sources) a single request could
take tens of seconds to minutes — see
`docs/phase6_agent_handoff.md` §8 for the exact bound (Phase 6's own
collection limits already cap the worst case there). No infinite hang is
possible (every service call this phase wraps has its own bounded
execution — sentiment/topic/aspect batch over a finite review set,
collection is capped by Phase 6's `SCRAPER_MAX_*` limits, report/summary
generation are bounded single operations).

**Why not fixed now:** "Do not introduce distributed infrastructure solely
for appearances" — a real background-cancellable workflow needs a task
queue (Celery/RQ) and a worker process, which no phase of this project has
introduced, and doing so just for cancellation would be exactly the kind
of infrastructure-for-appearances the brief warns against.

**Future solution:** If workflows grow to include a genuinely slow step
(e.g. a future LLM call with real network latency), revisit background
execution — at that point the cost is justified by a real need, not
speculative.

**Affected files:** `app/services/workflow_service.py`, `app/routes/workflows.py`.

**Risk:** Low — bounded worst-case execution time, no infinite hang.
**Migration required:** Possibly, if background execution is added later
(would need workflow status to support an actual "in progress, can be
polled" state — the current `agent_workflows.status` column already has
room for this without a schema change, just different service logic).

---

### D7-03 — Idempotency key has no expiry

**Component:** `app/models/agent_workflow.py`, `app/services/workflow_service.py::start_workflow`.

**Issue:** `(project_id, idempotency_key)` is enforced unique forever — a
client that reuses the same key later (not just for an accidental
double-click) will always get the original workflow's result back, never
a fresh run, with no time-based expiry.

**Temporary behavior:** The frontend always generates a fresh key per
click (`ui-${Date.now()}-${random}` — see `AgenticWorkflowPanel.jsx`), so
this only matters for a caller that deliberately reuses a key across
distinct real intents, which no current caller does.

**Future solution:** If a caller ever needs "retry the same logical
request key after some time has passed," add a TTL check (e.g. only treat
an existing row as a duplicate if `created_at` is within N minutes) rather
than changing the uniqueness guarantee itself.

**Affected files:** `app/services/workflow_service.py`.

**Risk:** Low — purely a UX edge case for a caller pattern that doesn't
exist yet.
**Migration required:** No (a TTL check is application logic, not a schema change).
