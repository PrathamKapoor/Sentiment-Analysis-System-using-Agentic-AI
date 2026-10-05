"""Add persisted investigations, activities, and evidence-linked findings.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from app.utils.uuid_type import GUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("investigations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("organisation_id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("requested_by", GUID(), nullable=False),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5", name="ck_investigation_attempts"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','WAITING','COMPLETED','FAILED','CANCELLED','LIMIT_REACHED','NEEDS_REVIEW')", name="ck_investigation_status"),
        sa.CheckConstraint("review_state IN ('UNREVIEWED','NEEDS_REVIEW','REVIEWED')", name="ck_investigation_review_state"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "requested_by", "idempotency_key", name="uq_investigation_idempotency"))
    op.create_index("ix_investigations_organisation_id", "investigations", ["organisation_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_index("ix_investigations_project_id", "investigations", ["project_id"])
    op.create_index("ix_investigations_claim", "investigations", ["status", "lease_until", "created_at"])
    op.create_index("ix_investigations_project_created", "investigations", ["project_id", "created_at"])
    op.create_table("investigation_events",
        sa.Column("id", GUID(), nullable=False), sa.Column("investigation_id", GUID(), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("activity_summary", sa.String(500), nullable=False), sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_investigation_events_parent", "investigation_events", ["investigation_id", "created_at"])
    op.create_index("ix_investigation_events_investigation_id", "investigation_events", ["investigation_id"])
    op.create_table("investigation_findings",
        sa.Column("id", GUID(), nullable=False), sa.Column("investigation_id", GUID(), nullable=False),
        sa.Column("finding_type", sa.String(50), nullable=False), sa.Column("claim_status", sa.String(30), nullable=False),
        sa.Column("claim", sa.String(2000), nullable=False), sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True), sa.Column("recommended_action", sa.String(2000), nullable=True),
        sa.Column("review_state", sa.String(30), nullable=False), sa.Column("reviewed_by", GUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("review_notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_investigation_finding_confidence"),
        sa.CheckConstraint("claim_status IN ('FACT','OBSERVATION','CORRELATION','MODEL_INTERPRETATION','HYPOTHESIS','RECOMMENDATION')", name="ck_investigation_finding_claim_status"),
        sa.CheckConstraint("review_state IN ('UNREVIEWED','NEEDS_REVIEW','ACCEPTED','REJECTED')", name="ck_investigation_finding_review_state"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_investigation_findings_parent", "investigation_findings", ["investigation_id", "created_at"])
    op.create_index("ix_investigation_findings_investigation_id", "investigation_findings", ["investigation_id"])


def downgrade():
    op.drop_index("ix_investigation_findings_investigation_id", table_name="investigation_findings")
    op.drop_index("ix_investigation_findings_parent", table_name="investigation_findings")
    op.drop_table("investigation_findings")
    op.drop_index("ix_investigation_events_investigation_id", table_name="investigation_events")
    op.drop_index("ix_investigation_events_parent", table_name="investigation_events")
    op.drop_table("investigation_events")
    op.drop_index("ix_investigations_project_created", table_name="investigations")
    op.drop_index("ix_investigations_claim", table_name="investigations")
    op.drop_index("ix_investigations_project_id", table_name="investigations")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_index("ix_investigations_organisation_id", table_name="investigations")
    op.drop_table("investigations")
