"""Phase 3: sentiment_results, topics, review_topics.

Two documented deviations from the original Database Data Dictionary
snapshot (both flagged in the Phase 3 completion report, not silent):

1. sentiment_results has no created_at/updated_at columns, per the approved
   dictionary — analysed_at (row creation) and corrected_at (row update via
   manual correction) already serve those purposes.
2. review_topics gains `relevance_score`, which the original dictionary
   didn't have — added because Phase 3 explicitly requires it and the
   TF-IDF/KMeans topic algorithm has no meaningful substitute for it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sentiment_results",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("review_id", GUID(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sentiment_label", sa.String(10), nullable=False),
        sa.Column("positive_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("negative_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("neutral_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrected_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("review_id", name="uq_sentiment_result_review"),
        sa.CheckConstraint("positive_score BETWEEN 0 AND 1", name="ck_sentiment_positive_range"),
        sa.CheckConstraint("negative_score BETWEEN 0 AND 1", name="ck_sentiment_negative_range"),
        sa.CheckConstraint("neutral_score BETWEEN 0 AND 1", name="ck_sentiment_neutral_range"),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_sentiment_confidence_range"),
    )
    op.create_index("ix_sentiment_results_label", "sentiment_results", ["sentiment_label"])

    op.create_table(
        "topics",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_topic_project_name"),
    )
    op.create_index("ix_topics_project_id", "topics", ["project_id"])

    op.create_table(
        "review_topics",
        sa.Column("review_id", GUID(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("topic_id", GUID(), sa.ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("relevance_score", sa.Numeric(5, 4), nullable=True),
        sa.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1",
            name="ck_review_topic_relevance_range",
        ),
    )


def downgrade():
    op.drop_table("review_topics")
    op.drop_table("topics")
    op.drop_table("sentiment_results")
