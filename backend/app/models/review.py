from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, SoftDeleteMixin, utcnow


class Review(UUIDPrimaryKeyMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "reviews"
    __table_args__ = (
        db.CheckConstraint(
            "(data_source_id IS NOT NULL) != (dataset_id IS NOT NULL)",
            name="ck_review_single_origin",
        ),
    )

    project_id = db.Column(
        db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id = db.Column(db.ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    dataset_id = db.Column(db.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    text = db.Column(db.Text, nullable=False)
    reviewer_ref = db.Column(db.String(150), nullable=True)
    source = db.Column(db.String(100), nullable=True)
    rating = db.Column(db.Numeric(3, 1), nullable=True)
    review_date = db.Column(db.Date, nullable=True)
    is_spam = db.Column(db.Boolean, nullable=False, default=False)
    is_duplicate = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="reviews")
    dataset = db.relationship("Dataset", back_populates="reviews")
    sentiment_result = db.relationship(
        "SentimentResult", back_populates="review", uselist=False, cascade="all, delete-orphan"
    )
    topic_links = db.relationship(
        "ReviewTopic", back_populates="review", cascade="all, delete-orphan"
    )
    aspect_links = db.relationship(
        "AspectSentiment", back_populates="review", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "dataSourceId": str(self.data_source_id) if self.data_source_id else None,
            "datasetId": str(self.dataset_id) if self.dataset_id else None,
            "text": self.text,
            "reviewerRef": self.reviewer_ref,
            "source": self.source,
            "rating": float(self.rating) if self.rating is not None else None,
            "reviewDate": self.review_date.isoformat() if self.review_date else None,
            "isSpam": self.is_spam,
            "isDuplicate": self.is_duplicate,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
