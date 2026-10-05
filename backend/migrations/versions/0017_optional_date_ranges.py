"""Make report and summary date filters optional.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("ai_summaries", "reports"):
        constraint = "ck_ai_summary_date_range" if table == "ai_summaries" else "ck_report_date_range"
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.alter_column("date_range_start", existing_type=sa.Date(), nullable=True)
            batch.alter_column("date_range_end", existing_type=sa.Date(), nullable=True)
            batch.create_check_constraint(
                constraint,
                "date_range_start IS NULL OR date_range_end IS NULL OR date_range_end >= date_range_start",
            )


def downgrade():
    for table in ("reports", "ai_summaries"):
        constraint = "ck_ai_summary_date_range" if table == "ai_summaries" else "ck_report_date_range"
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.alter_column("date_range_start", existing_type=sa.Date(), nullable=False)
            batch.alter_column("date_range_end", existing_type=sa.Date(), nullable=False)
            batch.create_check_constraint(constraint, "date_range_end >= date_range_start")
