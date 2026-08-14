# Phase 7 Schema Changes — Reconciliation

## Reconciliation table

| Requested Phase 7 concept | Existing implementation | Action |
|---|---|---|
| `processing_jobs` | Does not exist (Phase 2 decision — status lives on the owning row) | Not reused for workflows — a workflow isn't a dataset-processing job, and this table doesn't exist to reuse regardless |
| `collection_jobs` | Does not exist (Phase 6 decision — status derived from `data_sources.last_collected_at` + `audit_logs`) | Not reused — same reasoning, and workflows aren't collection runs |
| Workflow/agent-task persistence | No existing table represents "one workflow's current state, scoped to a project" | **New table required** — see below |
| Per-agent-step event history | No existing table | Reuse `audit_logs` (`entity_type="agent_workflow"`) — same pattern Phase 6 used for collection history |
| Human approval state | No existing "approval" concept beyond each resource's own `approval_status`/`status` column (AiSummary, Recommendation, Alert) | Reuse those columns directly — the workflow layer never invents its own parallel approval state; `agent_workflows.status = "waiting_for_approval"` just reflects that an existing resource (currently: an AiSummary) is pending review |
| Idempotency / duplicate-start prevention | No existing mechanism | Added as a column + unique constraint on the new table (see below) — not a separate table |

## Why a new table was genuinely necessary (unlike Phase 6)

Phase 6 needed zero new tables because every piece of collection state had
somewhere to live already: `data_sources.last_collected_at` gave "current
state" a home, and `audit_logs` gave history a home — *scoped by
`entity_id` = the source's own row*, which already carried `project_id`
via its own foreign key.

A **workflow** has no such existing row to attach to. It's a new concept:
"one orchestration run, scoped to a project, with its own lifecycle." The
two operations that expose this gap:

1. **`GET /projects/{id}/workflows`** — list workflows for a project. This
   requires filtering by `project_id`. `audit_logs` has **no `project_id`
   column** (only `organisation_id` — see `app/models/audit_log.py`), and
   using the workflow's own synthetic ID as `entity_id` doesn't help,
   because there's nothing else to join through to recover which project
   a given `entity_id` belongs to without a table that stores that mapping
   in the first place. This is exactly the case the Phase 7 brief's own
   database policy anticipates: "If resumable workflow state genuinely
   requires a new table... propose the minimal `agent_workflows`."
2. **Current-state queries** (`GET /workflows/{id}`, list ordering by
   recency/status) need an efficiently queryable "current row," not a
   derived-from-history computation — Phase 6's status derivation worked
   because there was always exactly one natural "latest state" question
   (per source); a workflow list needs sorting/filtering across many
   workflows at once, which is what an indexed table row is for.

## Schema change made

**Migration `0007_agent_workflows.py`** — one new table:

```sql
CREATE TABLE agent_workflows (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  workflow_type VARCHAR(30) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  options JSON NOT NULL DEFAULT '{}',
  idempotency_key VARCHAR(100),
  result_summary JSON NOT NULL DEFAULT '{}',
  started_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (project_id, idempotency_key)
);
CREATE INDEX ix_agent_workflows_project_id ON agent_workflows (project_id);
CREATE INDEX ix_agent_workflows_project_id_created_at ON agent_workflows (project_id, created_at);
CREATE INDEX ix_agent_workflows_project_id_status ON agent_workflows (project_id, status);
```

**Deliberately minimal — what's NOT in this table:**
- **No `agent_tasks` child table.** Per-step results live in
  `result_summary` (a bounded JSON list — step name/status/message/data/
  warnings, never full review text or LLM prompts) on the workflow row
  itself, written once when the workflow finishes (or pauses/resumes).
  This mirrors how Phase 5 used `content`/`rule_condition`/
  `generation_parameters` JSON columns instead of extra child tables for
  bounded, structured, non-relational data.
- **No separate approval-state table.** `status = "waiting_for_approval"`
  plus the step data already recorded in `result_summary` (which contains
  e.g. `summaryId` for the summary that needs approving) is sufficient —
  approving/rejecting acts on the *existing* resource (`ai_summaries`),
  not on a new workflow-specific approval row.
- **No `agent_workflows.organisation_id` column**, even though every other
  major table in this schema denormalizes it — deliberately omitted
  because `project_id` alone is sufficient for every query this table
  needs to serve (list-by-project, get-by-id via the same tenant-scoped
  decorator pattern every other resource uses), and `project.organisation_id`
  is one join away when audit logging needs it (see
  `workflow_service.py`, which always reads `workflow.project.organisation_id`).

**Verified:**
- `flask db upgrade` chain 0001→0007 runs cleanly against a throwaway
  SQLite DB.
- `flask db downgrade` → `flask db upgrade` on 0007 specifically, both
  directions clean.
- The model's `__table_args__` indexes match the migration exactly, so
  `db.create_all()` (used by the test suite) and `flask db upgrade` (used
  in real deployments) produce equivalent schemas.
