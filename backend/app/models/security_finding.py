from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin
from app.utils.uuid_type import GUID


class SecurityFinding(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Evidence-linked customer-reported security signal; never a confirmed incident by itself."""

    __tablename__ = "security_findings"
    __table_args__ = (
        db.UniqueConstraint("review_id", "finding_type", name="uq_security_finding_review_type"),
        db.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_security_finding_confidence"),
    )

    organisation_id = db.Column(GUID(), db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = db.Column(GUID(), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    review_id = db.Column(GUID(), db.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_type = db.Column(db.String(80), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    evidence = db.Column(db.JSON, nullable=False)
    indicators = db.Column(db.JSON, nullable=False, default=list)
    classification_method = db.Column(db.String(80), nullable=False)
    review_text_sha256 = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="needs_review")
    analyst_notes = db.Column(db.String(2000), nullable=True)
    reviewed_by = db.Column(GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    project = db.relationship("Project")
    review = db.relationship("Review")

    def to_dict(self):
        category_by_type = {
            "ACCOUNT_COMPROMISE": "ACCOUNT_SECURITY",
            "PERSONAL_DATA_EXPOSURE": "DATA_EXPOSURE",
            "PAYMENT_FRAUD": "PAYMENT_SECURITY",
            "PHISHING_OR_IMPERSONATION": "PHISHING",
            "AUTHENTICATION_FAILURE": "AUTHENTICATION",
            "MALWARE_REPORT": "MALWARE",
            "APPLICATION_VULNERABILITY_REPORT": "APPLICATION_SECURITY",
            "TLS_CERTIFICATE_FAILURE": "NETWORK_SECURITY",
        }
        return {
            "id": str(self.id), "organisationId": str(self.organisation_id),
            "projectId": str(self.project_id), "reviewId": str(self.review_id),
            "findingType": self.finding_type, "severity": self.severity,
            "category": category_by_type.get(self.finding_type, "OTHER"),
            "confidence": self.confidence, "evidence": self.evidence or [],
            "indicators": self.indicators or [], "classificationMethod": self.classification_method,
            "status": self.status, "analystNotes": self.analyst_notes,
            "reviewedBy": str(self.reviewed_by) if self.reviewed_by else None,
            "reviewedAt": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
