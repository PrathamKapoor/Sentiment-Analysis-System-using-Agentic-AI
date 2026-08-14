"""Phase 2: data_sources, datasets, reviews.

Dataset processing status/error tracking lives on the datasets table itself
(row_count/valid_row_count/invalid_row_count/duplicate_row_count/processing_error)
rather than a separate processing_jobs table — that table isn't part of the
approved 22-table schema, and dataset validate/process are short synchronous
operations in this phase (no Celery/Redis yet), so a job-tracking table would
have no concurrent-job case to justify it. See the Phase 2 completion report.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_sources",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_data_sources_project_id_enabled", "data_sources", ["project_id", "enabled"])

    op.create_table(
        "datasets",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("uploaded_by", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("valid_row_count", sa.Integer(), nullable=True),
        sa.Column("invalid_row_count", sa.Integer(), nullable=True),
        sa.Column("duplicate_row_count", sa.Integer(), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

    op.create_table(
        "reviews",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_source_id", GUID(), sa.ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dataset_id", GUID(), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("reviewer_ref", sa.String(150), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("rating", sa.Numeric(3, 1), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("is_spam", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(data_source_id IS NOT NULL) != (dataset_id IS NOT NULL)",
            name="ck_review_single_origin",
        ),
    )
    op.create_index("ix_reviews_project_id_review_date", "reviews", ["project_id", "review_date"])
    op.create_index("ix_reviews_project_id_is_spam", "reviews", ["project_id", "is_spam"])


def downgrade():
    op.drop_table("reviews")
    op.drop_table("datasets")
    op.drop_table("data_sources")
