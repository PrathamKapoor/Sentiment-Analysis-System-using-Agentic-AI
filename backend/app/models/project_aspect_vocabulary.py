"""Per-project aspect vocabulary override.

The aspect analyzer (``app/services/aspect_analyzer.py``) falls back to a
fixed 13-aspect seed dictionary in ``app/services/aspect_config.py``.
This table lets a project override that dictionary with domain-specific
aspects and synonyms. The fallback rule is:

  - if a project has any ``ProjectAspectVocabulary`` rows, the
    analyzer's effective vocabulary is the union of (a) the project's
    custom aspects and (b) the global seed terms
  - if a project has no rows, only the global seed terms apply (the
    pre-existing behaviour)

The vocabulary row stores a ``canonical_name`` and a list of
``surface_forms``. The analyzer matches lowercase surface forms via a
word-boundary regex, identical to the existing global behaviour.
"""
from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ProjectAspectVocabulary(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "project_aspect_vocabulary"
    __table_args__ = (
        db.UniqueConstraint("project_id", "canonical_name", name="uq_project_aspect_vocab_canonical"),
        db.CheckConstraint("length(canonical_name) > 0", name="ck_project_aspect_vocab_name"),
    )

    project_id = db.Column(
        db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_name = db.Column(db.String(150), nullable=False)
    surface_forms = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    project = db.relationship("Project")

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "canonicalName": self.canonical_name,
            "surfaceForms": list(self.surface_forms or []),
            "isActive": bool(self.is_active),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
