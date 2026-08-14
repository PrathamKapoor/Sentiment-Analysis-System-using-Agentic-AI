"""Phase 5: ai_summaries, alerts, reports.

All three tables use the approved Data Dictionary schema EXACTLY — no new
columns, no enum extensions. Every Phase 5 field with no backing column
lives inside an existing JSONB column (already documented as flexible
key-value storage), or is tracked via audit_logs:

- ai_summaries: summary_type/generation_method -> content JSONB.
  approval_status stays draft/approved/rejected (no pending_review — "submit
  for review" is an audited action, not a stored status).
- alerts: metric/operator/threshold/time_window/name/message -> rule_condition
  JSONB (whose own doc comment already gives exactly this shape). status
  stays open/resolved (no acknowledged — acknowledge is an audited action
  that doesn't change status). One row per rule (triggered_at IS NULL = not
  yet triggered) is itself the duplicate-trigger control.
- reports: report_name -> generation_parameters JSONB. file_format stays
  pdf/excel (not "xlsx").

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_summaries",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("approved_by", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("date_range_end >= date_range_start", name="ck_ai_summary_date_range"),
    )
    op.create_index("ix_ai_summaries_project_id_created_at", "ai_summaries", ["project_id", "created_at"])
    op.create_index("ix_ai_summaries_project_id_approval_status", "ai_summaries", ["project_id", "approval_status"])

    op.create_table(
        "alerts",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_condition", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_project_id_status", "alerts", ["project_id", "status"])
    op.create_index("ix_alerts_project_id_priority", "alerts", ["project_id", "priority"])
    op.create_index("ix_alerts_project_id_triggered_at", "alerts", ["project_id", "triggered_at"])
    op.create_index("ix_alerts_project_id_assigned_to", "alerts", ["project_id", "assigned_to"])

    op.create_table(
        "reports",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("generation_status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("generation_parameters", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("generated_by", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("date_range_end >= date_range_start", name="ck_report_date_range"),
    )
    op.create_index("ix_reports_project_id_created_at", "reports", ["project_id", "created_at"])
    op.create_index("ix_reports_project_id_generation_status", "reports", ["project_id", "generation_status"])
    op.create_index("ix_reports_project_id_file_format", "reports", ["project_id", "file_format"])


def downgrade():
    op.drop_table("reports")
    op.drop_table("alerts")
    op.drop_table("ai_summaries")
