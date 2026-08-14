# Phase 6 Schema Changes — Reconciliation

## Reconciliation table

| Requested Phase 6 concept | Existing implementation | Action |
|---|---|---|
| `data_sources` status/enable | Already exists (`enabled`, `last_collected_at`) | Reuse, unchanged |
| `processing_jobs` / `collection_jobs` table | Does not exist — Phase 2 established the precedent of tracking status directly on the owning row instead | Do not add. Collection is synchronous within the request, same as dataset validate/process (Phase 2) and every analysis run (Phase 3-5) |
| Collection job tracking (status/attempt count/error code) | `audit_logs` already exists with a flexible JSON `metadata` column | Reuse. Every collection attempt writes `collection.started`/`completed`/`failed`/`blocked_by_policy` with the full summary in metadata |
| Collection history | No DB table | Derived by querying `audit_logs` filtered to `entity_type='data_source'` — no new table |
| Collection status (current state) | No DB table | Derived from `data_sources.last_collected_at` (existing column) + the most recent relevant `audit_logs` row |
| Duplicate detection | `dataset_service.py` already has `normalize_for_dedup`-based text-hash dedup, project-scoped | Reuse directly — `collection_service.py` calls the same helper against the same existing-Review query pattern |
| Review ingestion / origin tracking | `reviews.data_source_id` + `ck_review_single_origin` constraint already exist and are already exercised by test fixtures since Phase 3 | Reuse. Collected reviews get `data_source_id` set, `dataset_id` null — no schema change |
| Source collection policy (allowed/blocked/api_preferred/etc) | No column | Computed dynamically per call (robots.txt + collector availability), never persisted — see `docs/phase6_deferred_issues.md` D6-03 |
| Per-source selector configuration | No column | Accepted as a transient per-call override only, never persisted — see D6-01 |
| Permissions for collection actions | `manage_data_sources` and `view_reviews` already exist and already gate data-source CRUD / review viewing | Reuse both — no new permission codes |
| `data_source_access_required` decorator | Already exists (`app/decorators/auth.py`) | Reuse directly for every new source-scoped route |
| Collection-status/history query performance | `audit_logs` only indexed `organisation_id` | **One new index** — see below, the only schema change this phase makes |

## Schema change made

**Migration `0006_audit_log_collection_index.py`** (index-only):

```sql
CREATE INDEX ix_audit_logs_entity_type_entity_id_timestamp
  ON audit_logs (entity_type, entity_id, timestamp);
```

- No new table, no new column, no data migration, no constraint change.
- Purely additive — safe to apply to a live database with no downtime
  concern beyond the (brief, size-dependent) index build itself.
- `downgrade()` drops the index; verified both directions against a
  throwaway SQLite DB (`flask db upgrade` → `flask db downgrade` →
  `flask db upgrade` again, all clean).
- The equivalent index is also declared on the `AuditLog` SQLAlchemy model
  (`app/models/audit_log.py::__table_args__`) so `db.create_all()` (used by
  the test suite) creates it too — migration and model stay in sync, same
  as every other index in this codebase.

## Why no `collection_jobs` table was created

The Phase 6 prompt's own database policy explicitly permits (and prefers)
this outcome: "ONLY add a new table if collection execution cannot be
represented safely using the current schema." It can:

1. **Status tracking** — collection is synchronous within one HTTP request
   (matches every prior phase's precedent for exactly this kind of
   "run something and report the result" operation). There is no concurrent
   "in-progress" state to track across requests, so a `status` column on a
   jobs table would only ever transition `queued → running → done` within
   a single function call — nothing reads it mid-flight.
2. **History** — `audit_logs` already exists specifically to record "who
   did what, when, with what result" across the whole system. Collection
   attempts fit that shape exactly: `collection.started`,
   `collection.completed` (with the full summary — recordsFound/Inserted/
   Duplicate/Invalid — in `metadata`), `collection.failed` (with
   `errorCode`/`safeErrorMessage`), `collection.blocked_by_policy`.
3. **"Last collection" at a glance** — `data_sources.last_collected_at`
   already exists in the approved schema for exactly this purpose.

Introducing `collection_jobs` would have duplicated data already tracked in
`audit_logs`, purely to save one indexed query — which is what the new
index in migration 0006 already buys, without a second source of truth to
keep in sync.
