"""Persist item-level source provenance on collected reviews.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reviews", sa.Column("source_record_id", sa.String(length=255), nullable=True))
    op.add_column("reviews", sa.Column("source_url", sa.String(length=2048), nullable=True))
    op.add_column("reviews", sa.Column("source_metadata", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("reviews", sa.Column("source_collected_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_reviews_data_source_record_id", "reviews", ["data_source_id", "source_record_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_reviews_data_source_record_id", table_name="reviews")
    op.drop_column("reviews", "source_collected_at")
    op.drop_column("reviews", "source_metadata")
    op.drop_column("reviews", "source_url")
    op.drop_column("reviews", "source_record_id")
