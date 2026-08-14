from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

PRIORITIES = ("low", "medium", "high")
# Approved schema had only new/assigned/completed. accepted/rejected added —
# a reject/accept workflow can't function on a 3-state enum with no
# "declined" state. See Phase 4 completion report.
STATUSES = ("new", "assigned", "accepted", "rejected", "completed")


class Recommendation(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "recommendations"

    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    aspect_id = db.Column(db.ForeignKey("aspects.id", ondelete="SET NULL"), nullable=True, index=True)
    text = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(10), nullable=False, default="medium")
    supporting_review_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    assigned_to = db.Column(db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="recommendations")
    aspect = db.relationship("Aspect", back_populates="recommendations")
    assignee = db.relationship("User")

    def to_dict(self, evidence=None):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "aspectId": str(self.aspect_id) if self.aspect_id else None,
            "aspectName": self.aspect.name if self.aspect else None,
            "text": self.text,
            "priority": self.priority,
            "supportingReviewCount": self.supporting_review_count,
            "status": self.status,
            "assignedTo": str(self.assigned_to) if self.assigned_to else None,
            "assignee": self.assignee.to_dict() if self.assignee else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "evidence": evidence,
        }
