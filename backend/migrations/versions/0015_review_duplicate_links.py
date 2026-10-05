"""Add provenance-preserving exact duplicate relationships.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
from app.utils.uuid_type import GUID


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_duplicate_links",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("review_id", GUID(), nullable=False),
        sa.Column("duplicate_review_id", GUID(), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("review_id != duplicate_review_id", name="ck_review_duplicate_not_self"),
        sa.CheckConstraint("strength IS NULL OR (strength >= 0 AND strength <= 1)", name="ck_review_duplicate_strength"),
        sa.CheckConstraint("relationship_type IN ('EXACT_DUPLICATE','NEAR_DUPLICATE','POSSIBLE_DUPLICATE')", name="ck_review_duplicate_type"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "duplicate_review_id", name="uq_review_duplicate_pair"),
    )
    op.create_index("ix_review_duplicate_links_project_id", "review_duplicate_links", ["project_id"])
    op.create_index("ix_review_duplicate_project", "review_duplicate_links", ["project_id", "created_at"])


def downgrade():
    op.drop_index("ix_review_duplicate_project", table_name="review_duplicate_links")
    op.drop_index("ix_review_duplicate_links_project_id", table_name="review_duplicate_links")
    op.drop_table("review_duplicate_links")
