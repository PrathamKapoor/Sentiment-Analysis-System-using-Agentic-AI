from app.extensions import db
from app.models.base import utcnow
from app.utils.uuid_type import GUID


class ProjectMember(db.Model):
    __tablename__ = "project_members"

    project_id = db.Column(
        GUID(), db.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    added_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="members")
    user = db.relationship("User")
