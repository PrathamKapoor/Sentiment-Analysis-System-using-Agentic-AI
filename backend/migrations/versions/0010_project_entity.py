"""Add canonical project entity and keyword groups.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_entities",
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("product", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("identifiers", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("include_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("exclude_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("security_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("competitor_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("custom_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("project_entities")
