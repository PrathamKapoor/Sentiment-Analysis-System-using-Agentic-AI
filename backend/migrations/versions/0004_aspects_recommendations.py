"""Phase 4: aspects, aspect_sentiments, recommendations.

Reviewed and approved resolutions (Phase 4 kickoff review), not silent
deviations:

1. aspects uses the approved schema EXACTLY: id, project_id, name. No
   normalized_name/description/frequency/created_at/updated_at. The
   canonical/normalized term is stored directly in `name`; frequency is
   computed dynamically from aspect_sentiments (same pattern as
   topics.frequency in Phase 3).
2. aspect_sentiments uses the approved schema EXACTLY: id, review_id,
   aspect_id, sentiment_label, confidence_score. No positive/negative/neutral
   scores, no evidence_text, no model metadata — label + confidence alone are
   sufficient to compute every field in the approved aspect-summary response;
   evidence snippets are derived on-demand from reviews.text.
3. recommendations.status is APPROVED to extend from new/assigned/completed
   to also include accepted/rejected — "Approved Phase 4 schema amendment
   required to support Accept/Reject recommendation workflow." priority
   stays exactly low/medium/high (no "critical").

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "aspects",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_aspect_project_name"),
    )
    op.create_index("ix_aspects_project_id", "aspects", ["project_id"])
    op.create_index("ix_aspects_project_id_name", "aspects", ["project_id", "name"])

    op.create_table(
        "aspect_sentiments",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("review_id", GUID(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aspect_id", GUID(), sa.ForeignKey("aspects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sentiment_label", sa.String(10), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.UniqueConstraint("review_id", "aspect_id", name="uq_aspect_sentiment_review_aspect"),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_aspect_sentiment_confidence_range"),
    )
    op.create_index("ix_aspect_sentiments_review_id", "aspect_sentiments", ["review_id"])
    op.create_index("ix_aspect_sentiments_aspect_id", "aspect_sentiments", ["aspect_id"])
    op.create_index("ix_aspect_sentiments_aspect_id_label", "aspect_sentiments", ["aspect_id", "sentiment_label"])

    op.create_table(
        "recommendations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aspect_id", GUID(), sa.ForeignKey("aspects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("supporting_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("assigned_to", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recommendations_project_id_status", "recommendations", ["project_id", "status"])
    op.create_index("ix_recommendations_project_id_priority", "recommendations", ["project_id", "priority"])
    op.create_index("ix_recommendations_project_id_aspect_id", "recommendations", ["project_id", "aspect_id"])
    op.create_index("ix_recommendations_project_id_assigned_to", "recommendations", ["project_id", "assigned_to"])


def downgrade():
    op.drop_table("recommendations")
    op.drop_table("aspect_sentiments")
    op.drop_table("aspects")
