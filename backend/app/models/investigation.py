from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.utils.uuid_type import GUID

INVESTIGATION_STATUSES = ("QUEUED", "RUNNING", "WAITING", "COMPLETED", "FAILED", "CANCELLED", "LIMIT_REACHED", "NEEDS_REVIEW")
FINDING_CLASSES = ("FACT", "OBSERVATION", "CORRELATION", "MODEL_INTERPRETATION", "HYPOTHESIS", "RECOMMENDATION")


class Investigation(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "investigations"
    __table_args__ = (
        db.UniqueConstraint("project_id", "requested_by", "idempotency_key", name="uq_investigation_idempotency"),
        db.CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5", name="ck_investigation_attempts"),
        db.CheckConstraint("status IN ('QUEUED','RUNNING','WAITING','COMPLETED','FAILED','CANCELLED','LIMIT_REACHED','NEEDS_REVIEW')", name="ck_investigation_status"),
        db.CheckConstraint("review_state IN ('UNREVIEWED','NEEDS_REVIEW','REVIEWED')", name="ck_investigation_review_state"),
        db.Index("ix_investigations_claim", "status", "lease_until", "created_at"),
        db.Index("ix_investigations_project_created", "project_id", "created_at"),
    )
    organisation_id = db.Column(GUID(), db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = db.Column(GUID(), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = db.Column(GUID(), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    question = db.Column(db.String(2000), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="QUEUED", index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    lease_owner = db.Column(db.String(100), nullable=True)
    lease_until = db.Column(db.DateTime(timezone=True), nullable=True)
    idempotency_key = db.Column(db.String(100), nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    error_code = db.Column(db.String(40), nullable=True)
    result_summary = db.Column(db.JSON, nullable=False, default=dict)
    review_state = db.Column(db.String(30), nullable=False, default="UNREVIEWED")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    project = db.relationship("Project")
    requester = db.relationship("User")
    events = db.relationship("InvestigationEvent", cascade="all, delete-orphan", order_by="InvestigationEvent.created_at")
    findings = db.relationship("InvestigationFinding", cascade="all, delete-orphan", order_by="InvestigationFinding.created_at")

    def to_dict(self, *, include_question=True):
        result = {"id": str(self.id), "organisationId": str(self.organisation_id), "projectId": str(self.project_id),
            "requestedBy": str(self.requested_by), "status": self.status, "attemptCount": self.attempt_count,
            "maxAttempts": self.max_attempts, "errorCode": self.error_code, "lastError": self.last_error,
            "result": self.result_summary or {}, "reviewState": self.review_state,
            "activities": [event.to_dict() for event in self.events],
            "findings": [finding.to_dict() for finding in self.findings],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None}
        if include_question:
            result["question"] = self.question
        return result


class InvestigationEvent(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "investigation_events"
    __table_args__ = (db.Index("ix_investigation_events_parent", "investigation_id", "created_at"),)
    investigation_id = db.Column(GUID(), db.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    activity_summary = db.Column(db.String(500), nullable=False)
    evidence_ids = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": str(self.id), "tool": self.tool_name, "status": self.status,
                "summary": self.activity_summary, "evidenceIds": self.evidence_ids or [],
                "createdAt": self.created_at.isoformat() if self.created_at else None}


class InvestigationFinding(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "investigation_findings"
    __table_args__ = (
        db.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_investigation_finding_confidence"),
        db.CheckConstraint("claim_status IN ('FACT','OBSERVATION','CORRELATION','MODEL_INTERPRETATION','HYPOTHESIS','RECOMMENDATION')", name="ck_investigation_finding_claim_status"),
        db.CheckConstraint("review_state IN ('UNREVIEWED','NEEDS_REVIEW','ACCEPTED','REJECTED')", name="ck_investigation_finding_review_state"),
        db.Index("ix_investigation_findings_parent", "investigation_id", "created_at"),
    )
    investigation_id = db.Column(GUID(), db.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_type = db.Column(db.String(50), nullable=False)
    claim_status = db.Column(db.String(30), nullable=False)
    claim = db.Column(db.String(2000), nullable=False)
    evidence_ids = db.Column(db.JSON, nullable=False, default=list)
    confidence = db.Column(db.Float, nullable=True)
    recommended_action = db.Column(db.String(2000), nullable=True)
    review_state = db.Column(db.String(30), nullable=False, default="NEEDS_REVIEW")
    reviewed_by = db.Column(GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    review_notes = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": str(self.id), "findingType": self.finding_type, "status": self.claim_status,
                "claim": self.claim, "evidenceIds": self.evidence_ids or [], "confidence": self.confidence,
                "recommendedAction": self.recommended_action, "reviewState": self.review_state,
                "reviewedBy": str(self.reviewed_by) if self.reviewed_by else None,
                "reviewedAt": self.reviewed_at.isoformat() if self.reviewed_at else None,
                "reviewNotes": self.review_notes, "createdAt": self.created_at.isoformat() if self.created_at else None}
