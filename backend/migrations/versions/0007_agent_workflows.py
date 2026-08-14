"""Phase 7: agent_workflows.

One new table, genuinely required — see docs/phase7_schema_changes.md.
Unlike Phase 6's collection status/history (which could be fully derived
from data_sources.last_collected_at + audit_logs), a "workflow" has no
existing row anywhere to derive project-scoped state from, and audit_logs
has no project_id column, so a project-scoped workflow list
(GET /projects/{id}/workflows) cannot be represented safely by audit_logs
alone. Per-agent-step event history still lives in audit_logs
(entity_type="agent_workflow") — only the workflow's own current-state row
is new.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

from app.utils.uuid_type import GUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_workflows",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_by", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_agent_workflow_idempotency"),
    )
    op.create_index("ix_agent_workflows_project_id", "agent_workflows", ["project_id"])
    op.create_index("ix_agent_workflows_project_id_created_at", "agent_workflows", ["project_id", "created_at"])
    op.create_index("ix_agent_workflows_project_id_status", "agent_workflows", ["project_id", "status"])


def downgrade():
    op.drop_table("agent_workflows")
