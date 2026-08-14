# Database

Schema is managed entirely through Flask-Migrate/Alembic — see `backend/migrations/versions/0001_initial_schema.py` for the Phase 1 schema (10 tables: organisations, users, organisation_members, roles, permissions, role_permissions, member_roles, projects, project_members, audit_logs).

Full column-level reference: `C:\pratham_normaldev\Database Data Dictionary.md`.

## Applying the schema

```
cd backend
flask db upgrade
flask seed
```

`flask seed` populates the fixed permission catalogue and the 6 built-in roles (Organisation Owner, Organisation Administrator, Project Manager, Analyst, Data Collector, Viewer) with their default permission sets. It's idempotent — safe to run again.

## seed.sql

`seed.sql` in this folder is a plain-SQL equivalent of `flask seed`, for environments where you want to seed via `psql` directly instead of through the Flask CLI (e.g. a fresh Postgres instance before the app is deployed).

## demo_dataset.csv

A small (28-row), fully synthetic dataset for demonstrations — no real personal data. Covers positive/negative/neutral sentiment, multiple aspects (delivery, battery, customer service, screen, packaging, price), two intentional exact-text duplicates (to demonstrate duplicate detection), ratings 1–5, and a deliberate March→August 2026 trend from mostly-negative to mostly-positive (to demonstrate Sentiment Trends).

**To load it:** create a project, then in Dataset Management upload `demo_dataset.csv`, map `review_text`→text, `rating`→rating, `review_date`→date, then Validate → Process. Afterwards run sentiment/topic/aspect analysis (individually or via a `FULL_ANALYSIS` agentic workflow) to populate the rest of the demo.
