from flask import Blueprint, request, g

from app.extensions import db
from app.errors.exceptions import ValidationError, ForbiddenError
from app.schemas.recommendation_schemas import (
    GenerateRecommendationsSchema, UpdateRecommendationSchema, AssignRecommendationSchema,
)
from app.decorators.auth import (
    project_access_required, permission_required, recommendation_access_required,
)
from app.services import recommendation_service
from app.services.permission_service import has_permission
from app.services.audit_service import log_action
from app.utils.query_helpers import is_valid_uuid
from app.utils.responses import success_response

project_recommendations_bp = Blueprint("project_recommendations", __name__)
recommendations_bp = Blueprint("recommendations", __name__)


def _dict_with_evidence(recommendation):
    return recommendation.to_dict(evidence=recommendation_service.compute_evidence(recommendation))


# Generation reuses view_reviews — see the matching note in routes/analysis.py.
@project_recommendations_bp.route("/generate", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def generate_recommendations(project_id):
    data = GenerateRecommendationsSchema().load(request.get_json(silent=True) or {})
    created = recommendation_service.generate_recommendations(
        project_id, g.current_user.id, min_frequency=data.get("minFrequency")
    )
    return success_response(
        {"createdCount": len(created), "items": [_dict_with_evidence(r) for r in created]},
        message="Recommendations generated", status_code=201,
    )


@project_recommendations_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_recommendations(project_id):
    filters = {
        "status": request.args.get("status"),
        "priority": request.args.get("priority"),
        "aspectId": request.args.get("aspectId"),
        "assignedTo": request.args.get("assignedTo"),
    }
    if filters["aspectId"] and not is_valid_uuid(filters["aspectId"]):
        raise ValidationError("aspectId must be a valid UUID")
    if filters["assignedTo"] and not is_valid_uuid(filters["assignedTo"]):
        raise ValidationError("assignedTo must be a valid UUID")
    items = recommendation_service.list_recommendations(project_id, filters)
    return success_response({"items": [_dict_with_evidence(r) for r in items]})


@recommendations_bp.route("/<recommendation_id>", methods=["GET"])
@recommendation_access_required
@permission_required("view_reviews")
def get_recommendation(recommendation_id):
    return success_response(_dict_with_evidence(g.current_recommendation))


@recommendations_bp.route("/<recommendation_id>", methods=["PATCH"])
@recommendation_access_required
@permission_required("approve_ai_output")
def update_recommendation(recommendation_id):
    data = UpdateRecommendationSchema().load(request.get_json(force=True) or {})
    rec = recommendation_service.update_recommendation(g.current_recommendation, data)
    log_action(g.current_organisation_id, g.current_user.id, "recommendation.update", "recommendation", rec.id, data)
    db.session.commit()
    return success_response(_dict_with_evidence(rec), message="Recommendation updated")


@recommendations_bp.route("/<recommendation_id>/assign", methods=["POST"])
@recommendation_access_required
@permission_required("approve_ai_output")
def assign_recommendation(recommendation_id):
    data = AssignRecommendationSchema().load(request.get_json(force=True) or {})
    rec = recommendation_service.assign_recommendation(g.current_recommendation, data["userId"])
    log_action(g.current_organisation_id, g.current_user.id, "recommendation.assign", "recommendation", rec.id, data)
    db.session.commit()
    return success_response(_dict_with_evidence(rec), message="Recommendation assigned")


@recommendations_bp.route("/<recommendation_id>/accept", methods=["POST"])
@recommendation_access_required
@permission_required("approve_ai_output")
def accept_recommendation(recommendation_id):
    rec = recommendation_service.accept_recommendation(g.current_recommendation)
    log_action(g.current_organisation_id, g.current_user.id, "recommendation.accept", "recommendation", rec.id)
    db.session.commit()
    return success_response(_dict_with_evidence(rec), message="Recommendation accepted")


@recommendations_bp.route("/<recommendation_id>/reject", methods=["POST"])
@recommendation_access_required
@permission_required("approve_ai_output")
def reject_recommendation(recommendation_id):
    rec = recommendation_service.reject_recommendation(g.current_recommendation)
    log_action(g.current_organisation_id, g.current_user.id, "recommendation.reject", "recommendation", rec.id)
    db.session.commit()
    return success_response(_dict_with_evidence(rec), message="Recommendation rejected")


@recommendations_bp.route("/<recommendation_id>/complete", methods=["POST"])
@recommendation_access_required
def complete_recommendation(recommendation_id):
    # Per the approved REST API Spec: "assignee or approve_ai_output" — not
    # a single permission_required() gate, since the assignee themself may
    # lack approve_ai_output but should still be able to mark their own
    # assigned recommendation complete.
    is_assignee = (
        g.current_recommendation.assigned_to is not None
        and str(g.current_recommendation.assigned_to) == str(g.current_user.id)
    )
    if not is_assignee and not has_permission(g.current_membership, "approve_ai_output"):
        raise ForbiddenError("Only the assignee or a user with approve_ai_output may complete this recommendation")

    rec = recommendation_service.complete_recommendation(g.current_recommendation)
    log_action(g.current_organisation_id, g.current_user.id, "recommendation.complete", "recommendation", rec.id)
    db.session.commit()
    return success_response(_dict_with_evidence(rec), message="Recommendation completed")
