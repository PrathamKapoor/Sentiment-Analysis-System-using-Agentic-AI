from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, SoftDeleteMixin, utcnow


class Dataset(UUIDPrimaryKeyMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "datasets"

    FILE_TYPES = ("csv", "excel", "json")
    STATUS_UPLOADED = "uploaded"
    STATUS_VALIDATED = "validated"
    STATUS_PROCESSING = "processing"
    STATUS_PROCESSED = "processed"
    STATUS_FAILED = "failed"

    project_id = db.Column(
        db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_type = db.Column(db.String(20), nullable=False)
    file_path = db.Column(db.Text, nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    column_mapping = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_UPLOADED)
    uploaded_by = db.Column(db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    # Processing status/error tracking, kept on the dataset row itself rather than
    # a separate `processing_jobs` table — see Phase 2 completion report for why.
    row_count = db.Column(db.Integer, nullable=True)
    valid_row_count = db.Column(db.Integer, nullable=True)
    invalid_row_count = db.Column(db.Integer, nullable=True)
    duplicate_row_count = db.Column(db.Integer, nullable=True)
    processing_error = db.Column(db.Text, nullable=True)

    # Quality-profile report computed by ``dataset_profile_service``.
    # Nullable: existing datasets and any new dataset that hasn't been
    # profiled yet keep ``profile_report = NULL`` and continue to behave
    # exactly as before. The profile is a diagnostic, never a blocker.
    profile_report = db.Column(db.JSON, nullable=True)
    profile_computed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    project = db.relationship("Project", back_populates="datasets")
    reviews = db.relationship("Review", back_populates="dataset")

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "fileType": self.file_type,
            "originalFilename": self.original_filename,
            "columnMapping": self.column_mapping,
            "status": self.status,
            "uploadedBy": str(self.uploaded_by),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "rowCount": self.row_count,
            "validRowCount": self.valid_row_count,
            "invalidRowCount": self.invalid_row_count,
            "duplicateRowCount": self.duplicate_row_count,
            "processingError": self.processing_error,
            "profileReport": self.profile_report,
            "profileComputedAt": self.profile_computed_at.isoformat() if self.profile_computed_at else None,
        }
