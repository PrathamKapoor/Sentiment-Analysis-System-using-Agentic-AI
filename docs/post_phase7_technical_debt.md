# Post-Phase 7 Technical Debt Register

Combines every unresolved item from `pre_phase6_technical_debt.md`,
`phase6_deferred_issues.md`, and `phase7_deferred_issues.md`, updated
during the Final QA / Demo Readiness pass with fixes made and priorities
reclassified per that pass's explicit guidance (Reddit/LangGraph/local
LLM/scheduler → P3 unless demo-required; background execution → P2, not
P1 for this synchronous academic design; historical PostgreSQL verification
debt was resolved on 2026-08-14). **No P0 (security/data integrity) issues are open.**

Priority key: **P0** security/data integrity · **P1** functionality ·
**P2** quality/performance · **P3** enhancement.

---

## Fixed during Final QA (no longer open)

- **Real PostgreSQL verification** — the historical Final QA record below
  correctly described an unverified environment at that time. It was resolved
  on 2026-08-14 against a real local PostgreSQL 18.6 server: empty-database
  migration `0001` through `0007`, seed idempotency, `0007 -> 0006 -> 0007`,
  schema/constraint/index inspection, and the full PostgreSQL-backed backend
  suite all passed. A PostgreSQL date-parameter compatibility defect found in
  that run was fixed with regression coverage. See
  `postgresql_verification_report.md`.

- **Workflow could get stuck at `status: "running"` forever if the
  orchestrator itself raised an unexpected exception** (distinct from an
  individual agent failing, which was already handled). Found while
  testing item 5 of this QA pass. Fixed: `workflow_service.start_workflow`
  now catches any orchestration-level exception and marks the workflow
  `failed` with a safe message, same pattern used everywhere else in this
  codebase for "never leave a resource in a non-terminal state." Regression
  test added (`test_orchestration_level_crash_marks_workflow_failed_not_stuck_running`).
- **Collection concurrency race** — two collection requests running
  concurrently in the same process could interfere with each other's SSRF
  protection (`ssrf_safe_connections()` monkeypatches a shared module-level
  function). Fixed: a process-wide lock (`app/services/collection_service.py::_serialized_collection`)
  now serializes every test-connection/preview/collect call, with a bounded
  30s acquire timeout returning a new `COLLECTION_BUSY` (503) error rather
  than hanging indefinitely. Lock is guaranteed released via `finally`, even
  on exception. Regression tests added. **Documented limitation, not a
  gap**: this only protects the current single-process architecture — a
  multi-worker/distributed deployment would need a different, externally-
  coordinated mechanism (see README "Collection concurrency").
- **Excel report dates/timestamps were plain text, not native Excel date
  cells** (`reviewDate`, `triggeredAt` columns). Fixed:
  `excel_report_service.py` now parses them back to real `date`/`datetime`
  objects with an appropriate `number_format` before writing. Low-risk,
  purely additive — verified live (regenerated report, confirmed cell type
  is `datetime.date`/`datetime.datetime` with the correct format string).
- Two SQLAlchemy `Query.get()` legacy-API warnings introduced by this QA
  pass's own new test code were fixed immediately (`db.session.get(...)`)
  — same mechanical fix already applied to `test_reports.py` in the
  pre-Phase-6 pass.

---

## P0 — Security / Data Integrity

**None open.**

---

## P1 — Functionality

**None currently open.** The historical PostgreSQL item was resolved on
2026-08-14; its pre-resolution context is retained in the Fixed section.

---

## P2 — Quality / Performance

*(Reclassified down from P1 this pass, per explicit guidance: these are
real gaps but not blockers for a synchronous academic-scope demo.)*

2. **No background execution** — a workflow cannot be cancelled mid-run,
   and a hypothetically slow future step would hold the HTTP request open
   for its full duration (Phase 7 D7-02). Bounded and safe today (every
   underlying service call has its own execution cap — see
   `docs/phase6_agent_handoff.md` §8 for the worst-case bound); would only
   become a real problem if a slow external dependency (e.g. a real LLM
   call) is added without first solving this.

3. **`generate_report` permission gates two conceptually distinct actions**
   (AI summary generation and report generation) — no dedicated "generate
   summary" permission exists (Phase 5 debt). Functionally correct, just
   coarser than ideal.

4. **AI summary "submitted for review" doesn't survive a page refresh** —
   `submit_for_review()` is audit-log-only (correct per the approved
   `draft`/`approved`/`rejected` enum), but nothing currently reads that
   audit log back. Two possible fixes recorded in `pre_phase6_technical_debt.md`:
   a general `GET /audit-logs` endpoint, or a reviewed `pending_review`
   schema amendment.

5. **PDF report cosmetics** — a near-blank trailing page when content ends
   near a page boundary, and "average confidence" rendering as a raw
   decimal instead of a percentage like its neighboring rows. Both
   explicitly deferred as cosmetic-only; the Excel equivalent (date typing)
   was fixed this pass since it was lower-risk to fix than to defer.

6. **No persisted per-source scraping configuration** — selector and
   policy overrides are transient (one call only), since the approved
   `data_sources` schema has no column for either (Phase 6 D6-01, D6-03).

7. **Collection scheduling is manual-only** — no recurring/scheduled
   collection exists at either the Phase 6 collector layer or the Phase 7
   workflow layer (Phase 6 D6-04).

8. **`SCRAPER_ALLOW_PRIVATE_TARGETS`** is a security-relevant config flag
   (default off, environment-variable-only, zero override surface —
   re-verified by grep this pass, including across all Phase 7 additions)
   that should be hardened further (e.g. gated behind
   `FLASK_ENV == "development"`) or removed once a proper mock-server test
   fixture makes it unnecessary (Phase 6 D6-05).

9. **robots.txt policy checking is best-effort** — unreachable/absent
   robots.txt defaults to "allowed," which is correct behavior but worth
   restating clearly so "policy: allowed" is never read as a legal
   guarantee (Phase 6 D6-06).

10. **Pagination detection is heuristic** (`rel="next"`/`.next`/
    `.pagination-next` only) — sites with different pagination markup only
    yield page 1 (Phase 6 D6-07).

11. **`resume_workflow()` is narrower than its name suggests** — it only
    ever re-attempts the report step, correct for every workflow type
    Phase 7 defines today but would need generalizing if a second
    approval-gated step is ever introduced (Phase 7 D7-01).

12. **Idempotency keys never expire** — a deliberately-reused key returns
    the original workflow forever. Not a problem for the current frontend
    (fresh key per click); worth a TTL only if a caller ever needs "retry
    after some time" semantics (Phase 7 D7-03).

---

## P3 — Enhancement / Optional

*(Reclassified per explicit final-QA guidance: none of these block demo
readiness.)*

13. **Reddit collection doesn't work** — `PublicRedditCollector` always
    reports itself unavailable; no OAuth/listing-API integration exists
    (Phase 6 D6-02). **P3 — not required for demo** (dataset upload is the
    documented fallback for Reddit content).

14. **No LangGraph** (`PHASE7_DEFERRED_LANGGRAPH`) — a deliberate
    technology choice given this codebase's synchronous, dependency-light
    architecture throughout every phase, not a capability gap.

15. **No external/local LLM provider** (`PHASE7_DEFERRED_LLM_PROVIDER`) —
    by design; the system is required to work with `DeterministicProvider`
    alone, and does. The `TextGenerationProvider` interface is ready for a
    real implementation whenever one exists to test against.

16. **`vaderSentiment`'s `codecs.open()` DeprecationWarning** — third-party
    library code, not ours; no safe fix without an unrequested dependency
    change.

17. **One expected `SAWarning`** in `tests/test_topics.py` — a Phase 3
    negative test intentionally creates a duplicate composite-PK row to
    verify a DB constraint; the warning is a benign side effect of that
    intentional test, not a defect.

18. **Secure Source/API Fallback** — **Experimental isolated prototype**
    only. It demonstrates AES-256-GCM credential encryption with
    RSA-OAEP-SHA256 key wrapping, an approved source registry, deterministic
    fallback resolution, provenance, bounded retries, and explicit no-data
    termination. It has no production imports, route/model/migration/UI
    changes, or source approvals. Promotion requires the separately reviewed
    CollectionService integration path documented under
    `future_enhancements/secure_source_fallback/`.

---

## What must be fixed before demonstration

**Nothing.** No P0 issues exist, tenant isolation/permissions/audit/
approval gates all work (re-verified live this pass), and every feature
degrades gracefully when something optional is unavailable (no LLM, no
Reddit credentials, no enabled sources). PostgreSQL verification is complete;
see `postgresql_verification_report.md`.

## What can safely be fixed after demonstration

Every P2/P3 item above (2–17) — all isolated, documented, non-destructive,
and don't affect the correctness of what's already working. If picked up,
recommended order: item 2 (background execution) first since it's the only
remaining P2 with real architectural weight; the rest are independent and
can be done in any order.
