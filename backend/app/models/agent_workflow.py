from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

# Phase 7: minimal new table. Steps/agent-level event history live in
# audit_logs (entity_type="agent_workflow"), same split Phase 6 used for
# collection status/history. A dedicated table was genuinely needed here
# (unlike Phase 6) because audit_logs has no project_id column, and
# GET /projects/{id}/workflows needs an efficient project-scoped list —
# see docs/phase7_schema_changes.md.
WORKFLOW_TYPES = (
    "FULL_ANALYSIS", "COLLECT_AND_ANALYSE", "REFRESH_ANALYSIS",
    "EXECUTIVE_BRIEF", "ALERT_RECHECK", "REPORT_REFRESH",
)
WORKFLOW_STATUSES = (
    "pending", "running", "completed", "completed_with_warnings",
    "failed", "cancelled", "waiting_for_approval",
)


class AgentWorkflow(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "agent_workflows"
    __table_args__ = (
        # NULL idempotency_key values are never considered equal by SQLite/
        # Postgres, so this only actually enforces uniqueness when a key is
        # supplied — exactly the "prevent double-click duplicate start" case.
        db.UniqueConstraint("project_id", "idempotency_key", name="uq_agent_workflow_idempotency"),
        db.Index("ix_agent_workflows_project_id_created_at", "project_id", "created_at"),
        db.Index("ix_agent_workflows_project_id_status", "project_id", "status"),
    )

    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_type = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    # Requested options as submitted (booleans/small strings only — never
    # raw review text or generated content).
    options = db.Column(db.JSON, nullable=False, default=dict)
    idempotency_key = db.Column(db.String(100), nullable=True)
    # {"steps": [{"agent":..., "status":..., "message":..., "data":..., "warnings":[...]}], "warnings": [...]}
    # Bounded, structured summaries only — never full review corpora or LLM
    # prompts (there is no LLM in this phase; documented for when there is).
    result_summary = db.Column(db.JSON, nullable=False, default=dict)
    started_by = db.Column(db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project")
    starter = db.relationship("User")

    def to_dict(self):
        summary = self.result_summary or {}
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "workflowType": self.workflow_type,
            "status": self.status,
            "options": self.options or {},
            "startedBy": str(self.started_by),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "steps": summary.get("steps", []),
            "warnings": summary.get("warnings", []),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
