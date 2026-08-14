from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin


class Organisation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "organisations"

    name = db.Column(db.String(200), nullable=False)
    plan = db.Column(db.String(50), nullable=False, default="free")

    members = db.relationship(
        "OrganisationMember", back_populates="organisation", cascade="all, delete-orphan"
    )
    projects = db.relationship(
        "Project", back_populates="organisation", cascade="all, delete-orphan"
    )
    roles = db.relationship("Role", back_populates="organisation", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "plan": self.plan,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
