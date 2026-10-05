from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.utils.uuid_type import GUID


class ReviewDuplicateLink(UUIDPrimaryKeyMixin, db.Model):
    """A provenance-preserving relationship between two source review rows."""
    __tablename__ = "review_duplicate_links"
    __table_args__ = (
        db.UniqueConstraint("review_id", "duplicate_review_id", name="uq_review_duplicate_pair"),
        db.CheckConstraint("review_id != duplicate_review_id", name="ck_review_duplicate_not_self"),
        db.CheckConstraint("strength IS NULL OR (strength >= 0 AND strength <= 1)", name="ck_review_duplicate_strength"),
        db.CheckConstraint("relationship_type IN ('EXACT_DUPLICATE','NEAR_DUPLICATE','POSSIBLE_DUPLICATE')", name="ck_review_duplicate_type"),
        db.Index("ix_review_duplicate_project", "project_id", "created_at"),
    )

    project_id = db.Column(GUID(), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    review_id = db.Column(GUID(), db.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    duplicate_review_id = db.Column(GUID(), db.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    relationship_type = db.Column(db.String(30), nullable=False, default="EXACT_DUPLICATE")
    strength = db.Column(db.Float, nullable=True)
    method = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    review = db.relationship("Review", foreign_keys=[review_id])
    duplicate_review = db.relationship("Review", foreign_keys=[duplicate_review_id])

    def to_dict(self):
        return {
            "id": str(self.id), "projectId": str(self.project_id),
            "reviewId": str(self.review_id), "duplicateReviewId": str(self.duplicate_review_id),
            "relationshipType": self.relationship_type, "strength": self.strength,
            "method": self.method, "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
