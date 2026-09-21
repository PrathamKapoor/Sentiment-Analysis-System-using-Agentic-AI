from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "projects"

    organisation_id = db.Column(
        db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    product_or_topic = db.Column(db.String(200), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    # Optional public business-context URL. When set, the user can opt
    # into a single bounded public-page fetch at report time. The URL
    # is never required; the system works fully without it.
    website_url = db.Column(db.String(2048), nullable=True)

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"

    organisation = db.relationship("Organisation", back_populates="projects")
    members = db.relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan"
    )
    data_sources = db.relationship(
        "DataSource", back_populates="project", cascade="all, delete-orphan"
    )
    datasets = db.relationship(
        "Dataset", back_populates="project", cascade="all, delete-orphan"
    )
    reviews = db.relationship(
        "Review", back_populates="project", cascade="all, delete-orphan"
    )
    topics = db.relationship(
        "Topic", back_populates="project", cascade="all, delete-orphan"
    )
    aspects = db.relationship(
        "Aspect", back_populates="project", cascade="all, delete-orphan"
    )
    recommendations = db.relationship(
        "Recommendation", back_populates="project", cascade="all, delete-orphan"
    )
    ai_summaries = db.relationship(
        "AiSummary", back_populates="project", cascade="all, delete-orphan"
    )
    alerts = db.relationship(
        "Alert", back_populates="project", cascade="all, delete-orphan"
    )
    reports = db.relationship(
        "Report", back_populates="project", cascade="all, delete-orphan"
    )
    aspect_vocabulary = db.relationship(
        "ProjectAspectVocabulary", back_populates="project", cascade="all, delete-orphan"
    )
    website_context = db.relationship(
        "ProjectWebsiteContext", uselist=False, cascade="all, delete-orphan", back_populates="project",
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "organisationId": str(self.organisation_id),
            "name": self.name,
            "description": self.description,
            "productOrTopic": self.product_or_topic,
            "startDate": self.start_date.isoformat() if self.start_date else None,
            "endDate": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "websiteUrl": self.website_url,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
