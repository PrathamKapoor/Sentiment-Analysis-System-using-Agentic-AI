from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

PRIORITIES = ("low", "medium", "high")
STATUSES = ("open", "resolved")  # exactly approved — see Phase 5 completion report
METRICS = (
    "negative_sentiment_percentage", "negative_review_count", "average_rating",
    "keyword_frequency", "aspect_negativity_percentage", "review_volume",
    "recommendation_priority",
)
OPERATORS = (">", ">=", "<", "<=", "==")


class Alert(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "alerts"

    # Approved schema exactly. metric/operator/threshold/time_window/name/
    # alert_message (Phase 5 brief fields with no backing column) all live
    # inside `rule_condition` — its own doc-comment example is exactly
    # {"metric":..., "operator":..., "threshold":...}. created_by isn't a
    # column — tracked via audit_logs, matching the recommendations.
    # generated_by precedent from Phase 4.
    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_condition = db.Column(db.JSON, nullable=False)
    priority = db.Column(db.String(10), nullable=False, default="medium", index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    triggered_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    assigned_to = db.Column(db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="alerts")
    assignee = db.relationship("User")

    @property
    def effective_status(self):
        """Computed, not stored: active/triggered/disabled/acknowledged/resolved."""
        if not self.enabled:
            return "disabled"
        if self.status == "resolved":
            return "resolved"
        if self.triggered_at is not None:
            return "acknowledged" if (self.rule_condition or {}).get("acknowledgedAt") else "triggered"
        return "active"

    def to_dict(self):
        condition = self.rule_condition or {}
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "name": condition.get("name") or f"{condition.get('metric')} {condition.get('operator')} {condition.get('threshold')}",
            "metric": condition.get("metric"),
            "operator": condition.get("operator"),
            "thresholdValue": condition.get("threshold"),
            "timeWindowDays": condition.get("timeWindowDays"),
            "severity": self.priority,
            "enabled": self.enabled,
            "status": self.status,
            "effectiveStatus": self.effective_status,
            "alertMessage": condition.get("lastEvaluation", {}).get("message"),
            "triggeredAt": self.triggered_at.isoformat() if self.triggered_at else None,
            "assignedTo": str(self.assigned_to) if self.assigned_to else None,
            "assignee": self.assignee.to_dict() if self.assignee else None,
            "resolutionNotes": self.resolution_notes,
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
