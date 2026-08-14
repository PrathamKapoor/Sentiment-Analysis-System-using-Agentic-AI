from datetime import datetime, timezone

from app.extensions import db
from app.errors.exceptions import ValidationError, ConflictError
from app.models import AiSummary, Project
from app.services.summary_service import generate_project_summary, SUMMARY_TYPES
from app.services.audit_service import log_action


def create_summary(project_id, actor_user_id, summary_type, date_from, date_to):
    if summary_type not in SUMMARY_TYPES:
        raise ValidationError(f"summaryType must be one of: {', '.join(SUMMARY_TYPES)}")
    if date_to < date_from:
        raise ValidationError("dateTo must not be before dateFrom")

    organisation_id = db.session.get(Project, project_id).organisation_id
    content = generate_project_summary(project_id, summary_type, date_from, date_to, actor_user_id)

    summary = AiSummary(
        project_id=project_id, date_range_start=date_from, date_range_end=date_to,
        content=content, approval_status="draft",
    )
    db.session.add(summary)
    db.session.flush()

    log_action(organisation_id, actor_user_id, "ai_summary.generated", "ai_summary", summary.id, {
        "summaryType": summary_type,
    })
    db.session.commit()
    return summary


def regenerate_summary(project_id, actor_user_id, summary_type, date_from, date_to):
    summary = create_summary(project_id, actor_user_id, summary_type, date_from, date_to)
    organisation_id = db.session.get(Project, project_id).organisation_id
    log_action(organisation_id, actor_user_id, "ai_summary.regenerated", "ai_summary", summary.id, {
        "summaryType": summary_type,
    })
    db.session.commit()
    return summary


def list_summaries(project_id):
    return AiSummary.query.filter_by(project_id=project_id).order_by(AiSummary.created_at.desc()).all()


def update_summary(summary, edited_sections, actor_user_id):
    if summary.approval_status == "approved":
        raise ConflictError("An approved summary cannot be edited — reject or regenerate instead")
    content = dict(summary.content or {})
    sections = dict(content.get("sections", {}))
    sections.update(edited_sections)
    content["sections"] = sections
    summary.content = content
    db.session.commit()
    log_action(summary.project.organisation_id, actor_user_id, "ai_summary.edited", "ai_summary", summary.id, {
        "editedSectionKeys": list(edited_sections.keys()),
    })
    db.session.commit()
    return summary


def submit_for_review(summary, actor_user_id):
    """No status column change (approval_status stays draft/approved/rejected
    per the approved schema) — this is a pure audit-logged workflow signal.
    """
    if summary.approval_status != "draft":
        raise ConflictError("Only a draft summary can be submitted for review")
    log_action(summary.project.organisation_id, actor_user_id, "ai_summary.submitted_for_review", "ai_summary", summary.id)
    db.session.commit()
    return summary


def approve_summary(summary, actor_user_id, edited_sections=None):
    if summary.approval_status == "approved":
        raise ConflictError("Summary is already approved")
    if not summary.content or not summary.content.get("sections"):
        raise ValidationError("Cannot approve an empty/unreviewed summary")

    if edited_sections:
        content = dict(summary.content or {})
        sections = dict(content.get("sections", {}))
        sections.update(edited_sections)
        content["sections"] = sections
        summary.content = content

    summary.approval_status = "approved"
    summary.approved_by = actor_user_id
    summary.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action(summary.project.organisation_id, actor_user_id, "ai_summary.approved", "ai_summary", summary.id)
    db.session.commit()
    return summary


def reject_summary(summary, actor_user_id, reason=None):
    if summary.approval_status == "approved":
        raise ConflictError("An approved summary cannot be rejected — regenerate instead")
    summary.approval_status = "rejected"
    summary.approved_by = actor_user_id
    summary.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action(summary.project.organisation_id, actor_user_id, "ai_summary.rejected", "ai_summary", summary.id, {
        "reason": reason,
    })
    db.session.commit()
    return summary
