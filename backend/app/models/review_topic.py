from app.extensions import db
from app.utils.uuid_type import GUID


class ReviewTopic(db.Model):
    __tablename__ = "review_topics"
    __table_args__ = (
        db.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1",
            name="ck_review_topic_relevance_range",
        ),
    )

    review_id = db.Column(GUID(), db.ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)
    topic_id = db.Column(GUID(), db.ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    # Not in the original Data Dictionary's review_topics (which had only the
    # two FK columns) — added because Phase 3 explicitly requires it and the
    # TF-IDF/KMeans topic algorithm has no meaningful substitute for it.
    # Duplicate (review_id, topic_id) pairs are prevented by the composite PK.
    relevance_score = db.Column(db.Numeric(5, 4), nullable=True)

    review = db.relationship("Review", back_populates="topic_links")
    topic = db.relationship("Topic", back_populates="review_links")
