import os
import uuid
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.errors.exceptions import ValidationError, NotFoundError
from app.models import Report, Project, AiSummary
from app.models.report import FILE_FORMATS
from app.services.report_data_service import gather_report_data, ALL_SECTIONS
from app.services.pdf_report_service import generate_pdf
from app.services.excel_report_service import generate_excel
from app.services.audit_service import log_action


def _output_dir():
    directory = current_app.config.get("REPORT_OUTPUT_DIRECTORY") or os.path.join(
        current_app.instance_path, "generated_reports"
    )
    os.makedirs(directory, exist_ok=True)
    return directory


def _validate_sections(sections):
    if not sections:
        raise ValidationError("At least one report section must be selected")
    unknown = set(sections) - set(ALL_SECTIONS)
    if unknown:
        raise ValidationError(f"Unknown section(s): {', '.join(sorted(unknown))}")


def create_report(project_id, actor_user_id, data):
    if data["fileFormat"] not in FILE_FORMATS:
        raise ValidationError(f"fileFormat must be one of: {', '.join(FILE_FORMATS)}")
    if data["dateTo"] < data["dateFrom"]:
        raise ValidationError("dateTo must not be before dateFrom")

    sections = list(data["sections"])
    if data.get("includeAiSummary") and "executiveSummary" not in sections:
        sections.append("executiveSummary")
    if data.get("includeRecommendations") and "recommendations" not in sections:
        sections.append("recommendations")
    if data.get("includeRepresentativeReviews") and "representativeReviews" not in sections:
        sections.append("representativeReviews")
    _validate_sections(sections)

    project = Project.query.filter_by(id=project_id).filter(Project.deleted_at.is_(None)).first()
    if project is None:
        raise NotFoundError("Project not found")
    organisation_id = project.organisation_id

    report = Report(
        project_id=project_id,
        date_range_start=data["dateFrom"],
        date_range_end=data["dateTo"],
        sections=sections,
        file_format=data["fileFormat"],
        generation_status="queued",
        generation_parameters={"reportName": data.get("reportName"), "requestedSections": sections},
        generated_by=actor_user_id,
    )
    db.session.add(report)
    db.session.flush()

    log_action(organisation_id, actor_user_id, "report.generation_started", "report", report.id, {
        "format": data["fileFormat"],
    })
    db.session.commit()

    file_path = None
    try:
        report.generation_status = "running"
        db.session.commit()

        ai_summary = None
        if "executiveSummary" in sections:
            ai_summary = (
                AiSummary.query.filter_by(project_id=project_id, approval_status="approved")
                .order_by(AiSummary.created_at.desc()).first()
            )

        sections_data, skipped = gather_report_data(
            project, sections, data["dateFrom"], data["dateTo"], ai_summary=ai_summary
        )

        extension = "pdf" if data["fileFormat"] == "pdf" else "xlsx"
        filename = f"{uuid.uuid4()}.{extension}"  # server-controlled, never user input
        file_path = os.path.join(_output_dir(), filename)

        organisation_name = project.organisation.name
        if data["fileFormat"] == "pdf":
            generate_pdf(file_path, organisation_name, project.name, data["dateFrom"], data["dateTo"], sections_data, skipped)
        else:
            generate_excel(file_path, organisation_name, project.name, data["dateFrom"], data["dateTo"], sections_data, skipped)

        report.file_path = file_path
        report.generation_status = "complete"
        params = dict(report.generation_parameters or {})
        params["sectionsIncluded"] = list(sections_data.keys())
        params["sectionsSkipped"] = skipped
        report.generation_parameters = params
        db.session.commit()

        log_action(organisation_id, actor_user_id, "report.generation_completed", "report", report.id, {
            "sectionsIncluded": list(sections_data.keys()),
        })
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if file_path and os.path.isfile(file_path):
            try:
                os.remove(file_path)  # never leave a partial/corrupt file unreferenced on disk
            except OSError:
                pass
        report = db.session.get(Report, report.id)
        report.generation_status = "failed"
        params = dict(report.generation_parameters or {})
        params["failureReason"] = str(exc)[:500]  # safe, bounded — no stack trace/internals
        report.generation_parameters = params
        db.session.commit()
        log_action(organisation_id, actor_user_id, "report.generation_failed", "report", report.id, {
            "error": str(exc)[:500],
        })
        db.session.commit()
        raise

    return report


def list_reports(project_id):
    return Report.query.filter_by(project_id=project_id).order_by(Report.created_at.desc()).all()


def get_report_file(report):
    if report.generation_status != "complete" or not report.file_path:
        raise ValidationError("Report is not ready for download")
    if not os.path.isfile(report.file_path):
        raise NotFoundError("Report file is missing on the server")
    return report.file_path


def delete_report(report, actor_user_id):
    organisation_id = report.project.organisation_id
    report_id = report.id
    if report.file_path and os.path.isfile(report.file_path):
        try:
            os.remove(report.file_path)
        except OSError:
            pass  # DB record removal still proceeds — a stray file isn't worth failing the request over
    db.session.delete(report)
    db.session.commit()
    log_action(organisation_id, actor_user_id, "report.deleted", "report", report_id)
    db.session.commit()
