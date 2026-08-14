from app.extensions import db
from app.utils.uuid_type import GUID, new_uuid

LABELS = ("positive", "negative", "neutral")


class AspectSentiment(db.Model):
    __tablename__ = "aspect_sentiments"
    __table_args__ = (
        db.UniqueConstraint("review_id", "aspect_id", name="uq_aspect_sentiment_review_aspect"),
        db.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_aspect_sentiment_confidence_range"),
    )

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    review_id = db.Column(GUID(), db.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    aspect_id = db.Column(GUID(), db.ForeignKey("aspects.id", ondelete="CASCADE"), nullable=False, index=True)
    sentiment_label = db.Column(db.String(10), nullable=False)
    confidence_score = db.Column(db.Numeric(5, 4), nullable=False)

    review = db.relationship("Review", back_populates="aspect_links")
    aspect = db.relationship("Aspect", back_populates="sentiment_links")

    def to_dict(self, evidence_text=None):
        return {
            "id": str(self.id),
            "reviewId": str(self.review_id),
            "aspectId": str(self.aspect_id),
            "aspectName": self.aspect.name if self.aspect else None,
            "sentimentLabel": self.sentiment_label,
            "confidenceScore": float(self.confidence_score),
            "evidenceText": evidence_text,
        }
