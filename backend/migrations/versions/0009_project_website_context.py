"""Phase 9: optional business-context website URL on projects + cached
single-page extraction table.

Three additive changes — existing rows and existing reports are
untouched:

1. ``projects.website_url`` (VARCHAR(2048), nullable). Optional. Lets
   the user attach a public business-context URL to a project so the
   enhanced-report mode can use it.

2. New table ``project_website_context`` (one row per project, unique
   on ``project_id``). Stores the most recent bounded single-page
   extraction: title, meta description, top headings, body excerpt,
   content hash, extraction status, failure reason, timestamp.

3. ``reports.mode`` (VARCHAR(16), NOT NULL, default 'standard'). Lets
   a report be explicitly requested as ``enhanced``. The renderer and
   the AI section honour this flag; the existing ``standard`` mode is
   the historical behaviour and is the default.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("website_url", sa.String(length=2048), nullable=True))

    op.create_table(
        "project_website_context",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("meta_description", sa.String(length=2048), nullable=True),
        sa.Column("headings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("body_excerpt", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", name="uq_project_website_context_project"),
    )
    op.create_index("ix_project_website_context_project_id", "project_website_context", ["project_id"])

    op.add_column(
        "reports",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="standard"),
    )


def downgrade():
    op.drop_column("reports", "mode")
    op.drop_index("ix_project_website_context_project_id", table_name="project_website_context")
    op.drop_table("project_website_context")
    op.drop_column("projects", "website_url")
