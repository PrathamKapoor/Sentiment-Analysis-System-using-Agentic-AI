from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow


class AuditLog(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # Phase 6: collection-status/collection-history read the most recent
        # audit_logs rows for one (entity_type, entity_id) ordered by time —
        # this is what makes that query cheap instead of a full table scan.
        db.Index("ix_audit_logs_entity_type_entity_id_timestamp", "entity_type", "entity_id", "timestamp"),
    )

    organisation_id = db.Column(
        db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor = db.Column(db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    # Mapped to the "metadata" column; "metadata" itself is reserved by SQLAlchemy's Base.
    event_metadata = db.Column("metadata", db.JSON, nullable=False, default=dict)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organisationId": str(self.organisation_id),
            "actor": str(self.actor),
            "action": self.action,
            "entityType": self.entity_type,
            "entityId": self.entity_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.event_metadata or {},
        }
