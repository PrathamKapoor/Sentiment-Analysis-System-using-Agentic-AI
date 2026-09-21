"""Phase 8: dataset profile + sentiment explainability + per-project aspect vocabulary.

Three additions, all additive — existing rows are untouched and continue to
work with NULL defaults.

1. ``datasets.profile_report`` (JSON, nullable) and
   ``datasets.profile_computed_at`` (timestamptz, nullable). The dataset
   service still functions as before when these are NULL — the profile is
   a diagnostic that is computed on demand.

2. ``sentiment_results.compound_score`` (Numeric(6,4), nullable) and
   ``sentiment_results.vader_breakdown`` (JSON, nullable). The compound
   score and per-token breakdown are written by the next automated or
   manual sentiment analysis run; existing rows are unaffected.

3. New table ``project_aspect_vocabulary`` (id, project_id, canonical_name,
   surface_forms JSON, is_active, created_at, updated_at). Unique on
   (project_id, canonical_name). ON DELETE CASCADE from projects. This
   lets a project override the global 13-aspect seed dictionary without
   breaking any existing aspect row or analysis.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Dataset profile
    op.add_column("datasets", sa.Column("profile_report", sa.JSON(), nullable=True))
    op.add_column("datasets", sa.Column("profile_computed_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Sentiment explainability
    op.add_column("sentiment_results", sa.Column("compound_score", sa.Numeric(6, 4), nullable=True))
    op.add_column("sentiment_results", sa.Column("vader_breakdown", sa.JSON(), nullable=True))

    # 3. Per-project aspect vocabulary
    op.create_table(
        "project_aspect_vocabulary",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_name", sa.String(150), nullable=False),
        sa.Column("surface_forms", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "canonical_name", name="uq_project_aspect_vocab_canonical"),
        sa.CheckConstraint("length(canonical_name) > 0", name="ck_project_aspect_vocab_name"),
    )
    op.create_index("ix_project_aspect_vocab_project_id", "project_aspect_vocabulary", ["project_id"])


def downgrade():
    op.drop_index("ix_project_aspect_vocab_project_id", table_name="project_aspect_vocabulary")
    op.drop_table("project_aspect_vocabulary")
    op.drop_column("sentiment_results", "vader_breakdown")
    op.drop_column("sentiment_results", "compound_score")
    op.drop_column("datasets", "profile_computed_at")
    op.drop_column("datasets", "profile_report")
