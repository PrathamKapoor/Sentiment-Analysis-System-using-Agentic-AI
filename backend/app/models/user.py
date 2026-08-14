import bcrypt

from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "users"

    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.Text, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    contact = db.Column(db.String(30), nullable=True)
    profile_photo_url = db.Column(db.Text, nullable=True)
    notification_prefs = db.Column(db.JSON, nullable=False, default=dict)

    memberships = db.relationship(
        "OrganisationMember", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, raw_password):
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "contact": self.contact,
            "profilePhotoUrl": self.profile_photo_url,
            "notificationPrefs": self.notification_prefs or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
