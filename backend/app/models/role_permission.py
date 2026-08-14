from app.extensions import db
from app.utils.uuid_type import GUID


class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    role_id = db.Column(
        GUID(), db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id = db.Column(
        GUID(), db.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role = db.relationship("Role", back_populates="role_permissions")
    permission = db.relationship("Permission")
