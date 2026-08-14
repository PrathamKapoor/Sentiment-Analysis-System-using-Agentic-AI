from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin


class Permission(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "permissions"

    code = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False, default="")

    def to_dict(self):
        return {"id": str(self.id), "code": self.code, "description": self.description}


# Fixed permission catalogue, per the approved SRS permission matrix.
PERMISSION_CATALOGUE = [
    ("create_project", "Create a project"),
    ("edit_project", "Edit, archive, or delete a project"),
    ("delete_project", "Delete a project"),
    ("upload_dataset", "Upload a dataset"),
    ("manage_data_sources", "Add, edit, enable, or disable data sources"),
    ("view_reviews", "View reviews and analysis results"),
    ("correct_sentiment", "Correct a review's sentiment label"),
    ("generate_report", "Generate, download, or delete reports"),
    ("manage_alerts", "Create, edit, or resolve alert rules"),
    ("manage_users", "Invite, edit, activate/deactivate, or remove users"),
    ("manage_roles", "Create, edit, or delete roles and assign permissions"),
    ("approve_ai_output", "Approve AI-generated summaries and recommendations"),
]
