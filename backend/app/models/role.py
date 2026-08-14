from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin

# The 6 built-in roles seeded with organisation_id = NULL.
BUILT_IN_ROLES = [
    "Organisation Owner",
    "Organisation Administrator",
    "Project Manager",
    "Analyst",
    "Data Collector",
    "Viewer",
]

# Default permission codes granted to each built-in role, per the SRS permission matrix.
DEFAULT_ROLE_PERMISSIONS = {
    "Organisation Owner": [
        "create_project", "edit_project", "delete_project", "upload_dataset",
        "manage_data_sources", "view_reviews", "correct_sentiment", "generate_report",
        "manage_alerts", "manage_users", "manage_roles", "approve_ai_output",
    ],
    "Organisation Administrator": [
        "create_project", "edit_project", "delete_project", "upload_dataset",
        "manage_data_sources", "view_reviews", "correct_sentiment", "generate_report",
        "manage_alerts", "manage_users", "manage_roles", "approve_ai_output",
    ],
    "Project Manager": [
        "create_project", "edit_project", "upload_dataset", "manage_data_sources",
        "view_reviews", "correct_sentiment", "generate_report", "manage_alerts",
        "approve_ai_output",
    ],
    "Analyst": [
        "upload_dataset", "view_reviews", "correct_sentiment", "generate_report",
        "manage_alerts",
    ],
    "Data Collector": ["upload_dataset", "manage_data_sources", "view_reviews"],
    "Viewer": ["view_reviews"],
}


class Role(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        db.UniqueConstraint("organisation_id", "name", name="uq_role_org_name"),
    )

    organisation_id = db.Column(
        db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name = db.Column(db.String(100), nullable=False)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)

    organisation = db.relationship("Organisation", back_populates="roles")
    role_permissions = db.relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    member_roles = db.relationship("MemberRole", back_populates="role")

    def permission_codes(self):
        return [rp.permission.code for rp in self.role_permissions]

    def to_dict(self):
        return {
            "id": str(self.id),
            "organisationId": str(self.organisation_id) if self.organisation_id else None,
            "name": self.name,
            "isCustom": self.is_custom,
            "permissions": self.permission_codes(),
        }
