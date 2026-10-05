"""Track source-review revisions associated with security evidence.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "security_findings",
        sa.Column("review_text_sha256", sa.String(length=64), nullable=True),
    )


def downgrade():
    op.drop_column("security_findings", "review_text_sha256")
