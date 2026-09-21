from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utcnow

FILE_FORMATS = ("pdf", "excel")  # approved enum — not "xlsx"
GENERATION_STATUSES = ("queued", "running", "complete", "failed")
# A report is either ``standard`` (deterministic findings only, no LLM)
# or ``enhanced`` (deterministic findings + optional AI-generated
# contextual interpretation when an LLM is configured). The two modes
# produce the same measured numbers; the enhanced mode adds a clearly
# labelled interpretation section.
REPORT_MODES = ("standard", "enhanced")


class Report(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        db.CheckConstraint("date_range_end >= date_range_start", name="ck_report_date_range"),
    )

    # Approved schema exactly. report_name (Phase 5 brief field, no backing
    # column) lives inside generation_parameters — it's JSONB, explicitly
    # documented as "full request snapshot for reproducibility". No
    # report_type/generated_at/updated_at columns.
    project_id = db.Column(db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    date_range_start = db.Column(db.Date, nullable=False)
    date_range_end = db.Column(db.Date, nullable=False)
    sections = db.Column(db.JSON, nullable=False, default=list)
    generation_parameters = db.Column(db.JSON, nullable=False, default=dict)
    # ``standard`` (default) or ``enhanced``. Enhanced reports may include
    # an AI-Generated Contextual Interpretation section when an LLM is
    # configured AND the project has an approved business-context URL.
    # Standard reports never include the AI section, regardless of config.
    mode = db.Column(db.String(16), nullable=False, default="standard")
    file_format = db.Column(db.String(10), nullable=False)
    file_path = db.Column(db.Text, nullable=True)
    generation_status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    generated_by = db.Column(db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    project = db.relationship("Project", back_populates="reports")
    generator = db.relationship("User")

    def to_dict(self):
        params = self.generation_parameters or {}
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "reportName": params.get("reportName") or f"Report {self.created_at.strftime('%Y-%m-%d') if self.created_at else ''}",
            "dateRangeStart": self.date_range_start.isoformat() if self.date_range_start else None,
            "dateRangeEnd": self.date_range_end.isoformat() if self.date_range_end else None,
            "sections": self.sections or [],
            "fileFormat": self.file_format,
            "generationStatus": self.generation_status,
            "generatedBy": str(self.generated_by),
            "generator": self.generator.to_dict() if self.generator else None,
            "mode": self.mode,
            "generationParameters": dict(self.generation_parameters or {}),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "hasFile": bool(self.file_path),
            # file_path itself is never exposed — download goes through the
            # authenticated /reports/{id}/download endpoint only.
        }
