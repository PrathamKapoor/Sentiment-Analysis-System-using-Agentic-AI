# Real PostgreSQL Verification Report

**Completed:** 2026-08-14
**Result:** PASS — real PostgreSQL verification completed.

## Environment and isolation

- Server discovered at `127.0.0.1:5432`: PostgreSQL 18.6 on Windows.
- Windows service: `postgresql-x64-18` (running).
- Client tools: `C:\Program Files\PostgreSQL\18\bin\psql.exe` and
  `pg_config.exe`.
- Authenticated server query returned PostgreSQL 18.6, database `postgres`,
  user `postgres`.
- Created two disposable databases: `sams_pg_validation` (migration/schema
  validation) and `sams_pg_integration` (test-suite isolation).
- Created a dedicated non-superuser, non-createdb, non-createrole login owner
  for both databases. Its generated password was only held in process memory
  and rotated for each verification process; no credential was written to the
  repository or this report.

## Migration and physical-schema validation

The validation database began with zero `public` tables. The actual Flask-
Migrate/Alembic command then applied the complete accepted chain:

```text
0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 -> 0007
```

Post-upgrade checks passed:

- `alembic_version`: `0007`.
- 23 production application base tables in `public`, excluding the separate
  `alembic_version` bookkeeping table.
- Native `uuid` columns were confirmed on representative primary keys
  (`organisations`, `users`, `agent_workflows`).
- Application JSON columns were confirmed as PostgreSQL `json` (the approved
  migrations use `sa.JSON`; no production `jsonb` column is expected),
  including `audit_logs.metadata`, `agent_workflows.options`, and
  `agent_workflows.result_summary`.
- Representative timestamps use `timestamp with time zone` (`timestamptz`).
- Foreign keys, unique constraints, checks, and indexes were inspected through
  PostgreSQL catalog views. This included `uq_users_email`, `uq_org_member`,
  `uq_role_org_name`, `ck_review_single_origin`, and
  `uq_agent_workflow_idempotency`.
- Phase 6's composite audit-history index was present exactly as
  `ix_audit_logs_entity_type_entity_id_timestamp` on
  `(entity_type, entity_id, timestamp)`.
- Phase 7's `agent_workflows` table, its project/user foreign keys, idempotency
  uniqueness constraint, and all three project-scoped indexes were present.

## Seed and migration reversibility

- `flask seed` passed twice. Counts before and after the second run were
  unchanged: 12 permissions, 6 built-in roles, and 42 role-permission links.
- Direct-parent downgrade `0007 -> 0006` passed: Alembic reported `0006`,
  `agent_workflows` no longer existed, and the Phase 6 audit index remained.
- Re-upgrade `0006 -> 0007` passed: Alembic returned to `0007`,
  `agent_workflows` returned, and the 23-table application count was restored.

## PostgreSQL-backed integration validation

`sams_pg_integration` was independently migrated from empty to `0007`, then
the complete backend suite was run with `TEST_DATABASE_URL` pointing to that
real PostgreSQL database.

```text
239 passed, 1 warning
```

This includes the existing integration coverage for authentication, RBAC,
cross-tenant resource hiding, ingestion and duplicate retention, sentiment,
topics, aspects, summaries/approval, workflow persistence/idempotency, alerts,
reports, and audit records. It is distinct from the normal SQLite-backed run.

## Compatibility defect found and fixed

The first PostgreSQL suite exposed two date-filter failures: analysis query
parameters arrived as strings and were compared directly with `DATE` columns.
SQLite accepted that comparison, while PostgreSQL correctly rejected it.

The minimal fix parses shared analysis date query parameters into Python
`date` objects and applies the same parsing to review-list date filters.
An invalid-date regression test was added. Verification after the fix:

```text
PostgreSQL targeted date/filter tests: 44 passed
PostgreSQL complete backend suite: 239 passed, 1 warning
SQLite complete backend suite: 239 passed, 1 warning
Experimental secure-source-fallback suite: 20 passed
Frontend production build: PASS
```

The sole warning is the existing intentional SQLAlchemy warning in the topic
composite-primary-key negative test. No migration `0008` was needed.

## Scope and safety notes

- No production imports from `future_enhancements/secure_source_fallback` were
  introduced; the prototype remains isolated.
- No PostgreSQL password, connection URL containing a password, or secret was
  committed.
- This validates database behavior and API/test flows, not a real browser
  walkthrough.

## Final status

```text
REAL POSTGRESQL CONNECTION ESTABLISHED: YES
EMPTY POSTGRESQL MIGRATION 0001 -> 0007: PASS
POSTGRESQL DOWNGRADE/RE-UPGRADE: PASS
POSTGRESQL SEED: PASS
POSTGRESQL CRITICAL INTEGRATION: PASS
CROSS-TENANT POSTGRESQL CHECK: PASS
POSTGRESQL VERIFIED: YES
```
