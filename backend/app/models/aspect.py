from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin


class Aspect(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "aspects"
    __table_args__ = (
        db.UniqueConstraint("project_id", "name", name="uq_aspect_project_name"),
    )

    # Approved schema exactly: id, project_id, name. No normalized_name,
    # description, frequency, created_at, or updated_at — frequency is
    # computed dynamically from aspect_sentiments, and `name` itself already
    # stores the normalized/canonical term (via ASPECT_SYNONYMS), so no
    # separate normalized_name column is needed.
    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)

    project = db.relationship("Project", back_populates="aspects")
    sentiment_links = db.relationship("AspectSentiment", back_populates="aspect", cascade="all, delete-orphan")
    recommendations = db.relationship("Recommendation", back_populates="aspect")

    def to_dict(self, frequency=None):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "name": self.name,
            "frequency": frequency,
        }
