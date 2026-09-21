import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.extensions import db
from app.errors.exceptions import ValidationError, NotFoundError
from app.models import Report, Project, AiSummary, ProjectWebsiteContext
from app.models.report import FILE_FORMATS, REPORT_MODES
from app.services.report_data_service import gather_report_data, ALL_SECTIONS, AI_INTERPRETATION_SECTION
from app.services.pdf_report_service import generate_pdf
from app.services.excel_report_service import generate_excel
from app.services.audit_service import log_action
from app.services.storage_service import get_storage


def _drop_local_file(file_path: str) -> None:
    """Remove the intermediate local file. The single source of truth is
    the storage backend; the file on disk is a staging area."""
    try:
        os.remove(file_path)
    except OSError:
        pass


def _store_generated_report(temp_path: str, filename: str) -> str:
    """Persist the rendered report into the configured storage backend.

    Returns the absolute filesystem path where the report can be read
    back from — what the existing callers (send_file, file stat/delete
    checks) expect. Behind a future object-storage backend this would
    no longer be a local path; the download route will need to adapt,
    but today the local backend provides this path.
    """
    key = filename
    with open(temp_path, "rb") as f:
        get_storage().save_bytes(f.read(), name=key)
    _drop_local_file(temp_path)
    return get_storage().resolve(key)


def _storage_key_for(file_path: str) -> str:
    """Storage key for the report. For the default LocalStorageBackend
    this is the report filename (a UUID); other backends may key by the
    same path if they implement on-path semantics."""
    return os.path.basename(file_path)


def _persist_report_file(file_path: str) -> None:
    """Store the file through the configured storage backend so a future
    object-storage adapter can intercept writes without the renderer
    knowing about it."""
    backend = get_storage()
    if hasattr(backend, "save_bytes") and callable(backend.save_bytes):
        with open(file_path, "rb") as f:
            backend.save_bytes(f.read(), name=_storage_key_for(file_path))
    # Local backend creates the file already at generation time; nothing
    # else to do.


def _save_generated_report(file_path: str) -> str:
    """Persist the completed report file via the configured storage
    backend and return the storage key equivalent to the file path when
    the local backend is in use. Returns the original file path string
    because the download flow uses a local file path today.
    """
    with open(file_path, "rb") as f:
        data = f.read()
    key = os.path.basename(file_path)
    get_storage().save_bytes(data, name=key)
    return file_path


def _validate_sections(sections):
    if not sections:
        raise ValidationError("At least one report section must be selected")
    unknown = set(sections) - set(ALL_SECTIONS)
    if unknown:
        raise ValidationError(f"Unknown section(s): {', '.join(sorted(unknown))}")


def _coerce_mode(value: Any) -> str:
    if value in (None, ""):
        return "standard"
    value = str(value).strip().lower()
    if value not in REPORT_MODES:
        raise ValidationError(f"mode must be one of: {', '.join(REPORT_MODES)}")
    return value


def _build_analytics_for_llm(project: Project, sections_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build the compact analytics dict the LLM prompt expects. This is
    aggregate numbers only — never raw review text, never per-review rows.
    """
    analytics: Dict[str, Any] = {
        "projectName": project.name,
        "organisationName": project.organisation.name if project.organisation else None,
    }

    if "sentimentDistribution" in sections_data:
        sd = sections_data["sentimentDistribution"]
        analytics["sentiment"] = {
            "positive": {"count": sd["positive"]["count"], "percentage": sd["positive"]["percentage"]},
            "negative": {"count": sd["negative"]["count"], "percentage": sd["negative"]["percentage"]},
            "neutral": {"count": sd["neutral"]["count"], "percentage": sd["neutral"]["percentage"]},
            "totalReviews": sd.get("totalReviews"),
            "analysedReviews": sd.get("analysedReviews"),
        }
        analytics["totalReviews"] = sd.get("totalReviews")
        analytics["eligibleReviews"] = sd.get("analysedReviews")

    if "sentimentTrends" in sections_data:
        st = sections_data["sentimentTrends"]
        periods = st.get("periods", [])
        if periods:
            analytics["trendDirection"] = _trend_direction(periods)

    if "topicAnalysis" in sections_data:
        analytics["topTopics"] = [t.get("topicName") for t in sections_data["topicAnalysis"][:5] if t.get("topicName")]

    if "keywordAnalysis" in sections_data:
        analytics["topKeywords"] = [k.get("keyword") for k in sections_data["keywordAnalysis"][:10] if k.get("keyword")]

    if "aspectSentiment" in sections_data:
        analytics["topAspects"] = sections_data["aspectSentiment"][:8]

    if "recommendations" in sections_data:
        analytics["openRecommendations"] = [
            r for r in sections_data["recommendations"] if r.get("status") in ("new", "assigned", "accepted")
        ]

    if "alerts" in sections_data:
        analytics["openAlerts"] = [a for a in sections_data["alerts"] if a.get("status") != "resolved"]

    # Dataset-quality flags if any dataset was processed for this project.
    try:
        from app.models import Dataset
        last_dataset = (
            Dataset.query.filter_by(project_id=project.id)
            .filter(Dataset.deleted_at.is_(None))
            .order_by(Dataset.created_at.desc()).first()
        )
        if last_dataset and last_dataset.profile_report:
            pr = last_dataset.profile_report
            analytics["datasetQuality"] = {
                "severity": pr.get("severity"),
                "warnings": pr.get("warnings") or [],
                "spamCount": pr.get("spamCount"),
                "duplicateRowCount": pr.get("duplicateRowCount"),
                "emptyTextRowCount": pr.get("emptyTextRowCount"),
            }
            analytics["spamCount"] = pr.get("spamCount")
            analytics["duplicateCount"] = pr.get("duplicateRowCount")
    except Exception:
        pass

    return analytics


def _trend_direction(periods) -> str:
    if not periods or len(periods) < 2:
        return "stable"
    last = periods[-1].get("positivePercentage", 0) or 0
    prev = periods[-2].get("positivePercentage", 0) or 0
    delta = last - prev
    if delta >= 3:
        return "improving"
    if delta <= -3:
        return "declining"
    return "stable"


def _build_business_context(project: Project) -> Optional[Dict[str, Any]]:
    if not project.website_url:
        return None
    row = ProjectWebsiteContext.query.filter_by(project_id=project.id).first()
    if row is None or row.status != "ok":
        return None
    return {
        "sourceUrl": row.source_url or project.website_url,
        "title": row.title or "",
        "metaDescription": row.meta_description or "",
        "headings": list(row.headings or []),
        "bodyExcerpt": row.body_excerpt or "",
    }


def create_report(project_id, actor_user_id, data):
    if data["fileFormat"] not in FILE_FORMATS:
        raise ValidationError(f"fileFormat must be one of: {', '.join(FILE_FORMATS)}")
    if data["dateTo"] < data["dateFrom"]:
        raise ValidationError("dateTo must not be before dateFrom")

    mode = _coerce_mode(data.get("mode"))

    sections = list(data["sections"])
    if data.get("includeAiSummary") and "executiveSummary" not in sections:
        sections.append("executiveSummary")
    if data.get("includeRecommendations") and "recommendations" not in sections:
        sections.append("recommendations")
    if data.get("includeRepresentativeReviews") and "representativeReviews" not in sections:
        sections.append("representativeReviews")
    if mode == "enhanced" and AI_INTERPRETATION_SECTION not in sections:
        # Enhanced mode always includes the AI section, even if the
        # caller didn't list it — that's the entire point of the mode.
        sections.append(AI_INTERPRETATION_SECTION)
    if mode == "standard" and AI_INTERPRETATION_SECTION in sections:
        # Standard mode NEVER includes the AI section, even if the
        # caller listed it. The rule "deterministic findings only"
        # trumps the caller-supplied list.
        sections = [s for s in sections if s != AI_INTERPRETATION_SECTION]
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
        mode=mode,
        generation_status="queued",
        generation_parameters={
            "reportName": data.get("reportName"),
            "requestedSections": sections,
            "mode": mode,
        },
        generated_by=actor_user_id,
    )
    db.session.add(report)
    db.session.flush()

    log_action(organisation_id, actor_user_id, "report.generation_started", "report", report.id, {
        "format": data["fileFormat"],
        "mode": mode,
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

        # First pass: deterministic sections only.
        sections_data, skipped = gather_report_data(
            project, sections, data["dateFrom"], data["dateTo"],
            ai_summary=ai_summary,
            ai_interpretation=None,
        )

        # Second pass: optionally generate AI interpretation. This is
        # done AFTER deterministic data so the prompt only sees the
        # numbers we actually rendered in the report.
        if mode == "enhanced" and AI_INTERPRETATION_SECTION in sections:
            from app.services.llm_service import interpret_analytics
            analytics_for_llm = _build_analytics_for_llm(project, sections_data)
            business_context = _build_business_context(project)
            ai_result = interpret_analytics(
                analytics_for_llm,
                business_context=business_context,
                actor_user_id=actor_user_id,
                organisation_id=organisation_id,
                project_id=project_id,
            )
            # Re-gather so the AI section is included in the rendered data.
            sections_data, skipped = gather_report_data(
                project, sections, data["dateFrom"], data["dateTo"],
                ai_summary=ai_summary,
                ai_interpretation=ai_result,
            )

        extension = "pdf" if data["fileFormat"] == "pdf" else "xlsx"
        filename = f"{uuid.uuid4()}.{extension}"
        # Render into a temporary file first, then persist through the
        # storage backend. Isolates the renderer from the storage
        # implementation so a future object-storage backend can plug in.
        temp_dir = tempfile.mkdtemp(prefix="report_gen_")
        temp_path = os.path.join(temp_dir, filename)

        organisation_name = project.organisation.name
        try:
            if data["fileFormat"] == "pdf":
                generate_pdf(temp_path, organisation_name, project.name, data["dateFrom"], data["dateTo"], sections_data, skipped)
            else:
                generate_excel(temp_path, organisation_name, project.name, data["dateFrom"], data["dateTo"], sections_data, skipped)
            file_path = _store_generated_report(temp_path, filename)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        report.file_path = file_path
        report.generation_status = "complete"
        params = dict(report.generation_parameters or {})
        params["sectionsIncluded"] = list(sections_data.keys())
        params["sectionsSkipped"] = skipped
        params["mode"] = mode
        if AI_INTERPRETATION_SECTION in sections_data:
            ai_meta = sections_data[AI_INTERPRETATION_SECTION]
            params["aiInterpretation"] = {
                "source": ai_meta.get("source"),
                "provider": ai_meta.get("provider"),
                "model": ai_meta.get("model"),
                "status": ai_meta.get("status"),
                "latencyMs": ai_meta.get("latencyMs"),
            }
        report.generation_parameters = params
        db.session.commit()

        log_action(organisation_id, actor_user_id, "report.generation_completed", "report", report.id, {
            "sectionsIncluded": list(sections_data.keys()),
            "mode": mode,
        })
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if file_path and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        report = db.session.get(Report, report.id)
        report.generation_status = "failed"
        params = dict(report.generation_parameters or {})
        params["failureReason"] = str(exc)[:500]
        report.generation_parameters = params
        db.session.commit()
        log_action(organisation_id, actor_user_id, "report.generation_failed", "report", report.id, {
            "error": str(exc)[:500],
            "mode": mode,
        })
        db.session.commit()
        raise

    return report


def list_reports(project_id):
    return Report.query.filter_by(project_id=project_id).order_by(Report.created_at.desc()).all()


def get_report_file(report):
    if report.generation_status != "complete" or not report.file_path:
        return None
    # ``file_path`` is the storage key (usually just the filename). Resolve
    # to the real local path the static file server can serve.
    path = get_storage().resolve(report.file_path)
    return path if os.path.isfile(path) else None


def delete_report(report, actor_user_id):
    organisation_id = report.project.organisation_id
    if report.file_path:
        try:
            get_storage().delete(report.file_path)
        except Exception:
            pass
    db.session.delete(report)
    db.session.commit()
    log_action(organisation_id, actor_user_id, "report.deleted", "report", report.id)
    db.session.commit()
    return report
