"""Persist deterministic project keyword matches on review records.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "reviews",
        sa.Column("keyword_matches", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("reviews", "keyword_matches")
