"""Cached per-project website context.

One row per project. The row is overwritten in place when the project
owner re-runs extraction. We do not version these — the user-controlled
``projects.website_url`` field is the source of truth, and the cache is
a snapshot of the most recent successful extraction.

Stored fields
-------------
  - ``website_url``     (string, nullable) — the user-supplied URL on
                        the project. Lives in the project row, mirrored
                        here for query convenience.
  - ``source_url``      (string)            — the normalized URL that
                        was actually fetched (after normalization, before
                        redirect resolution).
  - ``status``          (string)            — extraction status
                        (ok / blocked / fetch_failed / parse_failed /
                        too_large).
  - ``title``           (string, nullable)
  - ``meta_description``(string, nullable)
  - ``headings``        (JSON)
  - ``body_excerpt``    (text, nullable)
  - ``content_hash``    (string, nullable)  — SHA-256 of the raw HTML, for
                        drift detection.
  - ``failure_reason``  (string, nullable)  — safe string, never raw stack
                        trace.
  - ``extracted_at``    (timestamptz)
"""
from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ProjectWebsiteContext(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "project_website_context"

    project_id = db.Column(
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    website_url = db.Column(db.String(2048), nullable=True)
    source_url = db.Column(db.String(2048), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="ok")
    title = db.Column(db.String(512), nullable=True)
    meta_description = db.Column(db.String(2048), nullable=True)
    headings = db.Column(db.JSON, nullable=False, default=list)
    body_excerpt = db.Column(db.Text, nullable=True)
    content_hash = db.Column(db.String(64), nullable=True)
    failure_reason = db.Column(db.String(500), nullable=True)
    extracted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    project = db.relationship("Project", back_populates="website_context")

    def to_dict(self) -> dict:
        return {
            "projectId": str(self.project_id),
            "websiteUrl": self.website_url,
            "sourceUrl": self.source_url,
            "status": self.status,
            "title": self.title,
            "metaDescription": self.meta_description,
            "headings": list(self.headings or []),
            "bodyExcerpt": self.body_excerpt,
            "contentHash": self.content_hash,
            "failureReason": self.failure_reason,
            "extractedAt": self.extracted_at.isoformat() if self.extracted_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
