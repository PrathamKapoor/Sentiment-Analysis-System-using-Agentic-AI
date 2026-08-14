# Pre-Phase 6 Technical Debt

Recorded during a limited Phase 5 retrospective verification pass, before Phase 6 (data
collection) implementation begins. Nothing in Phase 5's design was changed as part of this
pass — see the completion notes below for what was actually touched (two bug fixes, one
`.gitignore` addition, this file).

---

## P1 — Real PostgreSQL validation required

**Status:** open, carried forward from every phase's completion report (Phase 1–5).

**Reason:** Migrations 0001–0005 and the full backend regression suite (146 tests) have only
ever been run against SQLite — an in-memory DB for automated tests, a throwaway file-based DB
for manual smoke tests. Docker's daemon has been unreachable in this sandbox at every phase
checkpoint (re-checked again during this pass), and no standalone PostgreSQL install is
available here. Every model already uses the cross-dialect `GUID`/`db.JSON` column types
specifically so the same code runs unchanged on both engines, but "should work" is not the
same as "verified."

**Required before final demonstration / production use:**
- Run the full `flask db upgrade` migration chain (0001 → latest) against a real PostgreSQL
  instance.
- Verify constraints (check constraints, foreign keys, unique constraints) and indexes are
  created as expected — SQLite is lenient about some constraint enforcement that Postgres is
  not.
- Run the complete backend test suite against Postgres (`TEST_DATABASE_URL` pointed at a real
  Postgres DB) to catch any dialect-specific behavior difference.
- Perform a tenant-isolation smoke test end-to-end against Postgres (register two orgs, confirm
  cross-org 404s hold under Postgres's actual query planner/constraints).
- Test `flask db downgrade` one step then `upgrade` again on the latest migration, to confirm
  the downgrade path is real and not just present syntactically.

**This does not require redesigning Phase 5** — it's a verification task against the existing
schema, not a schema change.

---

## Permission mapping technical debt

**Current implementation:** AI summary generation (`POST /projects/{id}/ai-summaries` and
`/regenerate`) reuses the `generate_report` permission — there is no dedicated
"generate AI summary" permission code in the approved catalogue, and `generate_report` was
judged the closest fit at Phase 5 kickoff (documented in that phase's completion report).
Report generation itself also uses `generate_report`, so the same permission code currently
gates two conceptually distinct actions (writing a summary vs. producing a downloadable
report).

**Not changed in this pass** — per this task's explicit scope, no permission codes were added
or modified.

**For Phase 7:** orchestration work must reuse this same effective permission mapping
(`generate_report` for summary/report generation, `approve_ai_output` for summary
approval, `manage_alerts` for alert CRUD/workflow, `manage_data_sources` for source
management) rather than inventing new permission codes. If Phase 7's orchestration surfaces a
real need to distinguish "generate a summary" from "generate a report" at the permission level,
that should be raised explicitly as a proposed schema/catalogue amendment before implementation
— not silently added.

---

## Alert history design — confirmed, no `alert_occurrences` table

Confirmed by code inspection (`app/services/alert_service.py`, `app/models/alert.py`):

- **`alerts` row = current rule/state.** One row per rule. `rule_condition` (JSONB) holds the
  live condition plus `lastEvaluation` (most recent evaluate result) and, once acknowledged,
  `acknowledgedAt`/`acknowledgedBy`. `triggered_at`, `status`, `resolved_at`,
  `resolution_notes` are all real columns reflecting the rule's *current* lifecycle position.
  `effective_status` (`active`/`triggered`/`acknowledged`/`resolved`/`disabled`) is computed
  fresh from these persisted fields on every read — never cached, never stored redundantly.
- **`audit_logs` = historical lifecycle events.** Every `alert.created` / `alert.triggered` /
  `alert.evaluated` / `alert.acknowledged` / `alert.resolved` / `alert.assigned` /
  `alert.deleted` action is written to `audit_logs` (entity_type=`alert`) at the time it
  happens, giving a full timeline without a dedicated history table.

This was verified, not changed. **No `alert_occurrences` table was created** — the existing
one-row-per-rule + audit-log-for-history design already satisfies "does acknowledgement survive
a restart," and does so via approved schema columns (see next section), not an in-memory or
API-response-only value.

---

## AI summary "submitted for review" — deliberate limitation (documented, not fixed)

**Approved schema:** `ai_summaries.approval_status` enum is exactly `draft` / `approved` /
`rejected` (confirmed against `Database Data Dictionary.md` §18 and `app/models/ai_summary.py`
— no `pending_review` value exists or was added).

`submit_for_review()` (`app/services/ai_summary_service.py`) is therefore correctly
audit-only: it writes an `ai_summary.submitted_for_review` audit log entry and does **not**
change `approval_status` (which would require a schema value that doesn't exist).

**Gap found (not fixed in this pass, per instructions):** nothing currently reads that audit
log back. There is no `GET /audit-logs` (or equivalent) endpoint anywhere in the API, and the
frontend's `AiSummaryPage.jsx` derives its badge and button set purely from `approvalStatus`.
Practical effect: after clicking "Submit for Review," the summary still shows as `draft` with
the "Submit for Review" button still visible — the action is real (it's in `audit_logs`,
survives a server restart) but there is currently no UI/API path that reconstructs "this draft
has already been submitted" after a page refresh. A second click also isn't blocked (the
service's `if summary.approval_status != "draft": raise ConflictError` check only guards
against submitting an *approved/rejected* summary a second time, not a repeat submission of the
same still-draft summary), so duplicate `submitted_for_review` audit entries can accumulate.

**Recommended future fix (not done here — would need a decision, not just a patch):** either
(a) add a general-purpose `GET /audit-logs` read endpoint (useful well beyond this one case) and
have the frontend check for an unresolved `submitted_for_review` entry, or (b) propose
`pending_review` as an explicit, reviewed schema amendment to `ai_summaries.approval_status`
(same pattern as Phase 4's `recommendations.status` amendment) if a real approval queue becomes
a hard requirement. Neither was done here — this task's scope was verification only, and the
existing behavior is functionally correct (nothing is lost, nothing is fabricated), just not
reflected in the UI after a refresh.

---

## Report file lifecycle — bug found and fixed

**Bug:** `report_service.create_report()` set `file_path` locally and only wrote it to
`report.file_path` (the DB column) on success. If PDF/Excel generation raised partway through
(e.g. ReportLab's `SimpleDocTemplate.build()` opens and writes to the target file
incrementally, before an exception could be raised mid-render), the partially-written file was
left on disk with no DB row referencing it — a silent orphan-file leak on every generation
failure.

**Fix applied:** `file_path` is now initialized to `None` before the `try` block; the `except`
handler removes the file from disk (best-effort, `OSError` swallowed) if it was created before
the failure, in addition to the existing `generation_status = "failed"` / bounded
`failureReason` handling. A new regression test
(`tests/test_reports.py::test_generation_failure_leaves_no_orphan_file`) monkeypatches
`generate_pdf` to write a partial file and then raise, and asserts the file no longer exists
after the request fails.

**Everything else verified correct, no changes needed:**
- Successful generation creates exactly one file, referenced by exactly one `Report.file_path`.
- `delete_report()` already removed the file from disk (best-effort) before deleting the DB row.
- Download (`GET /reports/{id}/download`) has no user-controlled path component anywhere —
  `file_path` comes straight from the DB column, which is always a server-generated UUID
  filename under `REPORT_OUTPUT_DIRECTORY`. Path traversal isn't structurally possible; existing
  test `test_path_traversal_attempt_blocked` confirms a traversal string in the URL just fails
  UUID validation (400/404) before any filesystem access.
- `.gitignore` already covered `backend/instance/` (the default location for both
  `generated_reports/` and `uploads/` when the corresponding env vars are unset). Added explicit
  `backend/generated_reports/` and `backend/uploads/` entries as well, in case
  `REPORT_OUTPUT_DIRECTORY`/`UPLOAD_FOLDER` are ever pointed outside `instance/`.

---

## PDF quality smoke check — P2 cosmetic items only

A full 10-section PDF (all sections, `includeAiSummary: true`) was generated end-to-end against
a live server with real ingested/analysed data and manually read. Result: **structurally
sound** — valid PDF, non-empty, organisation name + project name + date range in the header,
clear section headings, styled tables, no visible text/table overlap or clipping.

Two cosmetic (P2) items noted, **not fixed** per instructions ("do not redesign PDF styling in
this task"):
1. The final page can end up almost entirely blank except for the "sections omitted" note, when
   the last real content section ends near a page boundary — wastes a page, not a defect.
2. "Average confidence" in the Sentiment Distribution table renders as a raw decimal (`0.5338`)
   while every other row in the same table is a percentage — a minor formatting inconsistency
   inherited from `sentiment_service`'s existing output shape, not something introduced by the
   PDF renderer itself.

---

## Regression result

`python -m pytest -v` (venv): **all tests pass**, including the one new test added by the
report-lifecycle fix above. `npm run build`: clean.

Exact counts and command output are in the chat completion report for this task, not
duplicated here to avoid this file going stale the next time the suite grows.

---

## Blocking defects

**None.** No data-loss risk, no broken migration chain, no cross-tenant exposure, and no
authentication/security issue was found. The one real bug found (report orphan-file leak) was
low-severity (disk hygiene, not correctness or security) and has been fixed with a regression
test. Phase 6 is clear to begin.
