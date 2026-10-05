from app.extensions import db
from app.models.base import TimestampMixin
from app.utils.uuid_type import GUID


class ProjectEntity(db.Model, TimestampMixin):
    """Validated product/entity identity and keyword policy for one project."""

    __tablename__ = "project_entities"

    project_id = db.Column(
        GUID(), db.ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    brand = db.Column(db.String(120), nullable=True)
    product = db.Column(db.String(200), nullable=True)
    model = db.Column(db.String(120), nullable=True)
    sku = db.Column(db.String(120), nullable=True)
    canonical_url = db.Column(db.String(2048), nullable=True)
    aliases = db.Column(db.JSON, nullable=False, default=list)
    identifiers = db.Column(db.JSON, nullable=False, default=dict)
    include_keywords = db.Column(db.JSON, nullable=False, default=list)
    exclude_keywords = db.Column(db.JSON, nullable=False, default=list)
    security_keywords = db.Column(db.JSON, nullable=False, default=list)
    competitor_keywords = db.Column(db.JSON, nullable=False, default=list)
    custom_keywords = db.Column(db.JSON, nullable=False, default=list)

    project = db.relationship("Project", back_populates="entity")

    @property
    def canonical_name(self):
        prefix = " ".join(
            value.strip() for value in (self.brand, self.product)
            if value and value.strip()
        )
        model = (self.model or "").strip()
        if not model:
            return prefix

        existing_tokens = {token.casefold() for token in prefix.split()}
        model_tokens = model.split()
        missing_tokens = [token for token in model_tokens if token.casefold() not in existing_tokens]
        return " ".join(value for value in (prefix, " ".join(missing_tokens)) if value)

    def to_dict(self):
        return {
            "projectId": str(self.project_id),
            "brand": self.brand,
            "product": self.product,
            "model": self.model,
            "sku": self.sku,
            "canonicalUrl": self.canonical_url,
            "canonicalName": self.canonical_name,
            "aliases": list(self.aliases or []),
            "identifiers": dict(self.identifiers or {}),
            "includeKeywords": list(self.include_keywords or []),
            "excludeKeywords": list(self.exclude_keywords or []),
            "securityKeywords": list(self.security_keywords or []),
            "competitorKeywords": list(self.competitor_keywords or []),
            "customKeywords": list(self.custom_keywords or []),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
