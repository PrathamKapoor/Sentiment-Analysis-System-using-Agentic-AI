# Documentation Sync Report

Compares the actual implemented system (`C:\Sentiment Analysis Management System using Agentic AI`, Phases 1–7 plus
this Final QA pass) against the approved documentation vault
(`C:\pratham_normaldev`, treated as read-only for this report —
no vault files were modified). Findings verified by direct inspection of
the vault files listed, not inferred.

For each item: **documented behavior** → **actual behavior** → **mismatch**
→ **recommended documentation update**. No vault edits were made
automatically — mismatches are reported here for review first, per the
Final QA instructions.

---

### 1. `recommendations.status` enum

**Documented:** `Database Data Dictionary.md` §19 states:
`status | varchar(20) | ... | enum: new/assigned/completed`.

**Actual:** `app/models/recommendation.py` implements
`new/assigned/accepted/rejected/completed` — `accepted`/`rejected` were
added as an explicitly approved Phase 4 schema amendment (see that phase's
completion report and README "Recommendation Engine" section), required
because the approved UI/API workflow needs both Accept and Reject actions,
which the original three-value enum structurally couldn't support.

**Mismatch:** The vault's Data Dictionary was never updated after that
approved amendment — it still shows the pre-amendment three-value enum.

**Recommended update:** Change the enum in `Database Data Dictionary.md`
§19 to `new/assigned/accepted/rejected/completed`, with a note that this
was a reviewed Phase 4 amendment (not a silent deviation) — mirroring the
note already present in `C:\Sentiment Analysis Management System using Agentic AI\README.md` under "Recommendation
Engine."

---

### 2. Table count (22 → 23)

**Documented:** `Database Data Dictionary.md` "Key Points" states
**"22 tables, not 21"** and explains the `member_roles` addition. No
mention of a 23rd table anywhere in the vault.

**Actual:** Phase 7 added `agent_workflows` (migration `0007`), bringing
the real total to **23 tables**. This was a reviewed, documented deviation
(see `docs/phase7_schema_changes.md`) — not silent — but the vault itself
was never updated to reflect it, since the vault is out of scope during
implementation phases per this project's own working rule.

**Mismatch:** Vault says 22; actual schema has 23.

**Recommended update:** Add a "23. `agent_workflows`" entry to
`Database Data Dictionary.md`'s Table Reference (columns:
`id, project_id, workflow_type, status, options, idempotency_key,
result_summary, started_by, started_at, completed_at, created_at`, unique
constraint on `(project_id, idempotency_key)`), and update the "Key
Points" count from 22 to 23 with a one-line explanation matching the
`member_roles` precedent already established there.

---

### 3. `audit_logs` composite index (migration 0006)

**Documented:** No mention anywhere in `Database Data Dictionary.md` of
an index on `audit_logs(entity_type, entity_id, timestamp)` — the vault's
"Recommended Indexes" section only lists the general
`(organisation_id, ...)` pattern.

**Actual:** Migration `0006_audit_log_collection_index.py` added exactly
this composite index, required so `GET /sources/{id}/collection-status`
and `/collection-history` (Phase 6) and workflow history reads don't do a
full table scan.

**Mismatch:** Index-only addition, not reflected in the vault's index
list.

**Recommended update:** Add one line to `Database Data Dictionary.md`'s
"Recommended Indexes" section: `audit_logs(entity_type, entity_id,
timestamp)` — collection/workflow status and history reads.

---

### 4. Workflow/orchestration API endpoints — undocumented in the REST API Spec

**Documented:** `REST API Specification.md` has zero mentions of
"workflow," "orchestrat," or "LangGraph" — confirmed by direct search.

**Actual:** 8 real endpoints exist and are implemented/tested:
`POST/GET /projects/{id}/workflows`, `GET /workflows/{id}`,
`GET /workflows/{id}/steps`, `POST /workflows/{id}/{cancel,resume,approve,reject}`
(see `docs/agentic_architecture.md` for the full contract).

**Mismatch:** Complete absence, not an inaccuracy — the REST API Spec
predates Phase 7 and was never extended for it (consistent with every
other phase's pattern of the vault staying frozen during implementation).

**Recommended update:** Add a new "Workflow Orchestration" section to
`REST API Specification.md` documenting these 8 endpoints in the same
format as its existing sections (method, path, permission, request/
response shape, status codes) — content is already fully specified in
`docs/agentic_architecture.md` and `README.md`'s "Agentic Workflow
Orchestration" section and can be transcribed directly.

---

### 5. Orchestration technology (LangGraph) — SRS is compatible, not contradicted

**Documented:** `Software Requirement Specification.md`'s glossary defines
"Agentic AI" conceptually ("AI components... that take multi-step,
semi-autonomous actions," naming a "Summary Agent" and "Recommendation
Agent" as examples) but names no specific orchestration technology and
has no FR mandating LangGraph or any particular framework.

**Actual:** A custom deterministic orchestrator was implemented instead of
LangGraph — `PHASE7_DEFERRED_LANGGRAPH` in `docs/phase7_deferred_issues.md`.

**Mismatch:** **None** — the SRS never committed to a specific
orchestration technology, so the implementation doesn't contradict it.
Worth noting explicitly rather than leaving implicit.

**Recommended update:** Optional, low-priority. If the vault is ever
extended with an implementation/architecture note, state explicitly that
orchestration was implemented as a custom deterministic engine rather than
LangGraph, and why (see `docs/agentic_architecture.md`) — purely for
completeness, not to resolve a contradiction, since none exists.

---

### 6. Deterministic provider / no LLM — consistent with SRS intent

**Documented:** SRS glossary describes Agentic AI components by their
*behavior* (multi-step, semi-autonomous), not by requiring a large
language model specifically. The rest of the vault (page notes for
Summary/Recommendation) similarly describes template-style, not
generative, output.

**Actual:** `DeterministicProvider` (wrapping the Phase 5 template engine)
is the only `TextGenerationProvider` implementation; no LLM is configured
or required.

**Mismatch:** None — consistent with the documented intent.

**Recommended update:** None required.

---

### 7. Reddit collection — optional/unavailable, consistent with Phase 6 scope

**Documented:** Vault page notes for Data Source Management list `reddit`
as a supported source `type` value (matching the approved enum), without
specifying an implementation method.

**Actual:** `reddit`-type sources are accepted (schema-valid) but
`PublicRedditCollector` always reports itself unavailable without a real
OAuth/listing-API integration, which doesn't exist yet (Phase 6 D6-02).

**Mismatch:** Minor — the vault documents the *type* as supported without
distinguishing "accepted as a valid source type" from "actually
collectible." Not a contradiction since the vault never claimed a specific
collection mechanism.

**Recommended update:** Low priority. If updated, add a note to the Data
Source Management page that `reddit` sources are schema-supported but
require API credentials not yet integrated — matches the honest framing
already in `README.md`.

---

### 8. Synchronous architecture — undocumented but consistent

**Documented:** No vault document states whether analysis/collection/
workflow execution is synchronous or asynchronous — the topic simply
isn't addressed at the requirements level.

**Actual:** Every phase (1 through 7) is synchronous-within-one-HTTP-
request — no Celery/Redis/background workers anywhere in the codebase.

**Mismatch:** None — absence of a stated requirement, not a contradiction.

**Recommended update:** None required for correctness. Optional: if the
vault ever gains an architecture/NFR section, note the synchronous design
choice and its documented bound (`docs/phase6_agent_handoff.md` §8).

---

### 9. PostgreSQL verification status

**Documented:** SRS and Data Dictionary specify PostgreSQL as the target
database (UUID types, JSONB, etc.) without stating a verification
requirement.

**Actual:** No phase of this project, including this Final QA pass, has
ever run against real PostgreSQL — Docker's daemon is unreachable and no
local PostgreSQL install/binary exists in this sandbox (re-confirmed this
session via direct filesystem search, not just the daemon check). Every
migration and the full 214-test suite have only run against SQLite.

**Mismatch:** None in the sense of contradicting a stated requirement, but
worth flagging: the vault's schema is written *as if* targeting Postgres
specifically (native UUID, JSONB), and that target has never actually been
exercised.

**Recommended update:** None required in the vault itself (this is an
environment/infrastructure gap, not a documentation error). Tracked as the
sole open P1 in `docs/post_phase7_technical_debt.md` item 1.

---

## Summary

| # | Item | Severity | Vault edit needed? |
|---|---|---|---|
| 1 | `recommendations.status` enum stale | Real mismatch | Yes |
| 2 | Table count 22 → 23 (`agent_workflows`) | Real mismatch | Yes |
| 3 | `audit_logs` composite index undocumented | Real mismatch (minor) | Yes |
| 4 | Workflow API endpoints undocumented | Real gap (complete absence) | Yes |
| 5 | LangGraph not used | Not a mismatch | No (optional) |
| 6 | Deterministic provider only | Not a mismatch | No |
| 7 | Reddit unavailable | Minor gap | No (optional) |
| 8 | Synchronous architecture | Not a mismatch | No (optional) |
| 9 | PostgreSQL unverified | Environment gap, not doc error | No |

**No vault files were modified in producing this report**, per the Final
QA instructions — items 1–4 are the ones with an actual content mismatch
worth fixing; a human should review and approve before any vault edit is
made.
