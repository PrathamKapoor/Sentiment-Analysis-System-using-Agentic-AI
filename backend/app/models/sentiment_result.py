from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

LABELS = ("positive", "negative", "neutral")


class SentimentResult(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "sentiment_results"
    __table_args__ = (
        db.UniqueConstraint("review_id", name="uq_sentiment_result_review"),
        db.CheckConstraint("positive_score BETWEEN 0 AND 1", name="ck_sentiment_positive_range"),
        db.CheckConstraint("negative_score BETWEEN 0 AND 1", name="ck_sentiment_negative_range"),
        db.CheckConstraint("neutral_score BETWEEN 0 AND 1", name="ck_sentiment_neutral_range"),
        db.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_sentiment_confidence_range"),
    )

    # One row per review — re-analysis UPDATEs this row in place rather than
    # versioning, matching the approved schema's unique(review_id) constraint.
    review_id = db.Column(db.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    sentiment_label = db.Column(db.String(10), nullable=False)
    positive_score = db.Column(db.Numeric(5, 4), nullable=False)
    negative_score = db.Column(db.Numeric(5, 4), nullable=False)
    neutral_score = db.Column(db.Numeric(5, 4), nullable=False)
    confidence_score = db.Column(db.Numeric(5, 4), nullable=False)
    model_name = db.Column(db.String(100), nullable=False)
    model_version = db.Column(db.String(50), nullable=False)
    analysed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    corrected_by_user_id = db.Column(db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    corrected_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Per-token VADER lexicon breakdown (Phase 8 — explainability).
    # Nullable so existing rows (analysed before this column was added)
    # are unaffected. When present, the shape is the same as the
    # ``vader_breakdown`` block returned by ``VaderSentimentAnalyzer.analyze``:
    #   {"tokens": [{"token", "lowered", "valence", "matched"}, ...],
    #    "contributingTerms": {"positive": [...], "negative": [...]}}
    # This is a lexicon-lookup surface — it never represents an
    # "objective" sentiment judgment about the review.
    compound_score = db.Column(db.Numeric(6, 4), nullable=True)
    vader_breakdown = db.Column(db.JSON, nullable=True)

    review = db.relationship("Review", back_populates="sentiment_result")

    @property
    def is_manually_corrected(self):
        return self.corrected_by_user_id is not None

    def to_dict(self):
        return {
            "id": str(self.id),
            "reviewId": str(self.review_id),
            "sentimentLabel": self.sentiment_label,
            "positiveScore": float(self.positive_score),
            "negativeScore": float(self.negative_score),
            "neutralScore": float(self.neutral_score),
            "confidenceScore": float(self.confidence_score),
            "compoundScore": float(self.compound_score) if self.compound_score is not None else None,
            "modelName": self.model_name,
            "modelVersion": self.model_version,
            "analysedAt": self.analysed_at.isoformat() if self.analysed_at else None,
            "correctedByUserId": str(self.corrected_by_user_id) if self.corrected_by_user_id else None,
            "correctedAt": self.corrected_at.isoformat() if self.corrected_at else None,
            "isManuallyCorrected": self.is_manually_corrected,
            "vaderBreakdown": self.vader_breakdown,
        }
