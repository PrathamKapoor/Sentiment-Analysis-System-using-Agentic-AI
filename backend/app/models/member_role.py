from app.extensions import db
from app.models.base import utcnow
from app.utils.uuid_type import GUID


class MemberRole(db.Model):
    """Join table between organisation_members and roles.

    Exists so one organisation member can hold more than one role at once
    (e.g. Analyst + Data Collector) — this is the table that took the
    approved schema from 21 to 22 tables.
    """

    __tablename__ = "member_roles"

    organisation_member_id = db.Column(
        GUID(),
        db.ForeignKey("organisation_members.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id = db.Column(
        GUID(), db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    organisation_member = db.relationship("OrganisationMember", back_populates="member_roles")
    role = db.relationship("Role", back_populates="member_roles")
