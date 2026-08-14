"""Phase 6: index-only migration for collection status/history reads.

No new table. Data collection (web-scraping sources) reuses the existing
schema in full:
- data_sources: already has last_collected_at (approved schema, unchanged).
- reviews: already supports data_source_id-origin rows via the existing
  ck_review_single_origin constraint (unchanged, exercised since Phase 3's
  test fixtures).
- audit_logs: collection.started/completed/failed/blocked_by_policy/preview
  and data_source.test_connection entries ARE the collection history/status
  — no collection_jobs table. This migration adds the one index that read
  pattern needs: (entity_type, entity_id, timestamp), previously only
  organisation_id was indexed.

See docs/phase6_schema_changes.md for the full reconciliation.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-07
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_audit_logs_entity_type_entity_id_timestamp",
        "audit_logs", ["entity_type", "entity_id", "timestamp"],
    )


def downgrade():
    op.drop_index("ix_audit_logs_entity_type_entity_id_timestamp", table_name="audit_logs")
