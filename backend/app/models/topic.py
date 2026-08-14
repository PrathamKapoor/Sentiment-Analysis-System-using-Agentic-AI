from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow


class Topic(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "topics"
    __table_args__ = (
        db.UniqueConstraint("project_id", "name", name="uq_topic_project_name"),
    )

    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="topics")
    review_links = db.relationship("ReviewTopic", back_populates="topic", cascade="all, delete-orphan")

    def to_dict(self, review_count=None):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            # "topic_name" in the Phase 3 brief, "name" in the approved Data
            # Dictionary — exposed as topicName in the API, stored as `name`.
            "topicName": self.name,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "reviewCount": review_count,
        }
