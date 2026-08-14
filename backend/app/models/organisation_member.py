from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin, utcnow


class OrganisationMember(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "organisation_members"
    __table_args__ = (
        db.UniqueConstraint("organisation_id", "user_id", name="uq_org_member"),
    )

    organisation_id = db.Column(
        db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="invited")
    invited_at = db.Column(db.DateTime(timezone=True), nullable=True, default=utcnow)
    joined_at = db.Column(db.DateTime(timezone=True), nullable=True)

    organisation = db.relationship("Organisation", back_populates="members")
    user = db.relationship("User", back_populates="memberships")
    member_roles = db.relationship(
        "MemberRole", back_populates="organisation_member", cascade="all, delete-orphan"
    )

    STATUS_INVITED = "invited"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    def role_names(self):
        return [mr.role.name for mr in self.member_roles]

    def to_dict(self):
        return {
            "id": str(self.id),
            "organisationId": str(self.organisation_id),
            "userId": str(self.user_id),
            "status": self.status,
            "roles": self.role_names(),
            "user": self.user.to_dict() if self.user else None,
        }
