"""Rule-based recommendation generation — deterministic templates, not an
LLM. Works fully without any AI model; if a local model were ever wired in
to improve wording, the underlying rule/evidence stays the source of truth
and the output would still be clearly labelled system-generated (see the
`generated_by` note below — no such column exists, so this is enforced by
convention: every recommendation's text is template-produced here, never
freeform).

Recommendations are strictly advisory: nothing in this module ever mutates
a project, review, or any other business record. The only side effects are
creating/updating rows in `recommendations` itself, plus an audit log entry.
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.errors.exceptions import ValidationError, ConflictError
from app.models import Recommendation, Project
from app.services import aspect_service, trend_service
from app.services.audit_service import log_action

DEFAULT_MIN_FREQUENCY = 3
NEGATIVE_THRESHOLD_PCT = 50.0
OPEN_STATUSES = ("new", "assigned", "accepted")


def _priority_for(negative_pct):
    if negative_pct >= 75:
        return "high"
    if negative_pct >= 60:
        return "medium"
    return "low"


def _template_text(aspect_name, negative_pct, frequency):
    return (
        f"Review the {aspect_name} experience: {aspect_name}-related feedback is "
        f"{negative_pct}% negative across {frequency} analysed review(s), a high enough "
        f"share to warrant attention."
    )


def generate_recommendations(project_id, actor_user_id, min_frequency=None):
    min_frequency = min_frequency or current_app.config.get("RECOMMENDATION_MIN_FREQUENCY", DEFAULT_MIN_FREQUENCY)
    organisation_id = db.session.get(Project, project_id).organisation_id

    aspects = aspect_service.list_aspects(project_id)
    existing_open_aspect_ids = {
        str(r.aspect_id) for r in Recommendation.query.filter_by(project_id=project_id)
        .filter(Recommendation.status.in_(OPEN_STATUSES)).all() if r.aspect_id
    }

    created = []
    for aspect_stats in aspects:
        if aspect_stats["frequency"] < min_frequency:
            continue
        if aspect_stats["negativePercentage"] < NEGATIVE_THRESHOLD_PCT:
            continue
        if aspect_stats["id"] in existing_open_aspect_ids:
            continue  # an open recommendation for this aspect already exists

        recommendation = Recommendation(
            project_id=project_id,
            aspect_id=aspect_stats["id"],
            text=_template_text(aspect_stats["name"], aspect_stats["negativePercentage"], aspect_stats["frequency"]),
            priority=_priority_for(aspect_stats["negativePercentage"]),
            supporting_review_count=aspect_stats["frequency"],
            status="new",
        )
        db.session.add(recommendation)
        created.append(recommendation)

    db.session.flush()
    log_action(organisation_id, actor_user_id, "recommendation.generated", "project", project_id, {
        "createdCount": len(created), "candidatesConsidered": len(aspects),
    })
    db.session.commit()
    return created


def list_recommendations(project_id, filters=None):
    filters = filters or {}
    query = Recommendation.query.filter_by(project_id=project_id)
    if filters.get("status"):
        query = query.filter(Recommendation.status == filters["status"])
    if filters.get("priority"):
        query = query.filter(Recommendation.priority == filters["priority"])
    if filters.get("aspectId"):
        query = query.filter(Recommendation.aspect_id == filters["aspectId"])
    if filters.get("assignedTo"):
        query = query.filter(Recommendation.assigned_to == filters["assignedTo"])
    return query.order_by(Recommendation.created_at.desc()).all()


def compute_evidence(recommendation):
    if recommendation.aspect_id is None:
        return None
    aspect_detail = aspect_service.get_aspect_detail(recommendation.aspect)
    trend_data = trend_service.get_trends(recommendation.project_id, "monthly", {"aspectId": str(recommendation.aspect_id)})
    periods = trend_data["periods"]
    trend = "not available"
    if len(periods) >= 2:
        prev, latest = periods[-2], periods[-1]
        if latest["negativePercentage"] > prev["negativePercentage"]:
            trend = "increasing"
        elif latest["negativePercentage"] < prev["negativePercentage"]:
            trend = "decreasing"
        else:
            trend = "stable"

    return {
        "aspect": aspect_detail["name"],
        "supportingReviews": aspect_detail["frequency"],
        "negativePercentage": aspect_detail["negativePercentage"],
        "trend": trend,
    }


def update_recommendation(recommendation, data):
    if "text" in data:
        recommendation.text = data["text"]
    if "priority" in data:
        recommendation.priority = data["priority"]
    db.session.commit()
    return recommendation


def assign_recommendation(recommendation, user_id):
    from app.models import OrganisationMember
    membership = OrganisationMember.query.filter_by(
        organisation_id=recommendation.project.organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise ValidationError("Assignee is not a member of this organisation")
    recommendation.assigned_to = user_id
    recommendation.status = "assigned"
    db.session.commit()
    return recommendation


def _transition(recommendation, new_status, allowed_from):
    if recommendation.status not in allowed_from:
        raise ConflictError(
            f"Cannot move recommendation from '{recommendation.status}' to '{new_status}'"
        )
    recommendation.status = new_status
    if new_status == "completed":
        recommendation.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return recommendation


def accept_recommendation(recommendation):
    return _transition(recommendation, "accepted", allowed_from=("new", "assigned"))


def reject_recommendation(recommendation):
    return _transition(recommendation, "rejected", allowed_from=("new", "assigned"))


def complete_recommendation(recommendation):
    return _transition(recommendation, "completed", allowed_from=("new", "assigned", "accepted"))
