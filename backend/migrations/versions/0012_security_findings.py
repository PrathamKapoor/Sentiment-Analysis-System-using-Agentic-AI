"""Add evidence-linked customer security findings.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_findings",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("organisation_id", GUID(), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_id", GUID(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("indicators", sa.JSON(), nullable=False),
        sa.Column("classification_method", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="needs_review"),
        sa.Column("analyst_notes", sa.String(length=2000), nullable=True),
        sa.Column("reviewed_by", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "finding_type", name="uq_security_finding_review_type"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_security_finding_confidence"),
    )
    op.create_index("ix_security_findings_organisation_id", "security_findings", ["organisation_id"])
    op.create_index("ix_security_findings_project_id", "security_findings", ["project_id"])
    op.create_index("ix_security_findings_review_id", "security_findings", ["review_id"])


def downgrade():
    op.drop_index("ix_security_findings_review_id", table_name="security_findings")
    op.drop_index("ix_security_findings_project_id", table_name="security_findings")
    op.drop_index("ix_security_findings_organisation_id", table_name="security_findings")
    op.drop_table("security_findings")
