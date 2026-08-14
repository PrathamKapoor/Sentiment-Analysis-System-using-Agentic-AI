from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin


class DataSource(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "data_sources"

    TYPES = (
        "review_site", "ecommerce", "reddit", "forum", "blog", "news", "survey",
    )

    project_id = db.Column(
        db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = db.Column(db.String(50), nullable=False)
    url = db.Column(db.Text, nullable=False)
    # Stored as a JSON list rather than Postgres text[] so the same column works
    # unchanged against the SQLite test database (see app/utils/uuid_type.py for
    # the same cross-dialect tradeoff already made for UUID columns in Phase 1).
    keywords = db.Column(db.JSON, nullable=False, default=list)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_collected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)

    project = db.relationship("Project", back_populates="data_sources")

    def __init__(self, **kwargs):
        from app.models.base import utcnow
        kwargs.setdefault("created_at", utcnow())
        kwargs.setdefault("keywords", [])
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "type": self.type,
            "url": self.url,
            "keywords": self.keywords or [],
            "enabled": self.enabled,
            "lastCollectedAt": self.last_collected_at.isoformat() if self.last_collected_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
