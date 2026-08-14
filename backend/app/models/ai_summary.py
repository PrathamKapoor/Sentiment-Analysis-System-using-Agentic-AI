from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

APPROVAL_STATUSES = ("draft", "approved", "rejected")


class AiSummary(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "ai_summaries"
    __table_args__ = (
        db.CheckConstraint("date_range_end >= date_range_start", name="ck_ai_summary_date_range"),
    )

    # Approved schema exactly. summary_type/generation_method (Phase 5 brief
    # fields with no backing column) live inside `content` — it's JSONB
    # specifically documented as "sections as keyed JSON". No generated_by/
    # generated_at/updated_at columns: generation is tracked via audit_logs,
    # created_at is generation time.
    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    date_range_start = db.Column(db.Date, nullable=False)
    date_range_end = db.Column(db.Date, nullable=False)
    content = db.Column(db.JSON, nullable=False, default=dict)
    approval_status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    approved_by = db.Column(db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="ai_summaries")
    approver = db.relationship("User")

    def to_dict(self):
        content = self.content or {}
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "dateRangeStart": self.date_range_start.isoformat() if self.date_range_start else None,
            "dateRangeEnd": self.date_range_end.isoformat() if self.date_range_end else None,
            "summaryType": content.get("summaryType"),
            "generationMethod": content.get("generationMethod"),
            "generatedBy": content.get("generatedByUserId"),
            "sections": content.get("sections", {}),
            "approvalStatus": self.approval_status,
            "approvedBy": str(self.approved_by) if self.approved_by else None,
            "approvedAt": self.approved_at.isoformat() if self.approved_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "isAiGenerated": True,
        }
