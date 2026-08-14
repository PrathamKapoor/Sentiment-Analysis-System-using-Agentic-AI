from flask import Blueprint, request, g

from app.extensions import db
from app.schemas.ai_summary_schemas import (
    CreateSummarySchema, UpdateSummarySchema, ApproveSummarySchema, RejectSummarySchema,
)
from app.decorators.auth import (
    project_access_required, permission_required, ai_summary_access_required,
)
from app.services import ai_summary_service
from app.utils.responses import success_response

project_summaries_bp = Blueprint("project_ai_summaries", __name__)
summaries_bp = Blueprint("ai_summaries", __name__)


# Generation reuses generate_report — the approved REST API Spec documents
# summary generation as "generate_report-equivalent (summary generation)".
@project_summaries_bp.route("", methods=["POST"])
@project_access_required
@permission_required("generate_report")
def create_summary(project_id):
    data = CreateSummarySchema().load(request.get_json(force=True) or {})
    summary = ai_summary_service.create_summary(
        project_id, g.current_user.id, data["summaryType"], data["dateFrom"], data["dateTo"]
    )
    return success_response(summary.to_dict(), message="Summary generated", status_code=201)


@project_summaries_bp.route("/regenerate", methods=["POST"])
@project_access_required
@permission_required("generate_report")
def regenerate_summary(project_id):
    data = CreateSummarySchema().load(request.get_json(force=True) or {})
    summary = ai_summary_service.regenerate_summary(
        project_id, g.current_user.id, data["summaryType"], data["dateFrom"], data["dateTo"]
    )
    return success_response(summary.to_dict(), message="Summary regenerated", status_code=201)


@project_summaries_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_summaries(project_id):
    items = ai_summary_service.list_summaries(project_id)
    return success_response({"items": [s.to_dict() for s in items]})


@summaries_bp.route("/<summary_id>", methods=["GET"])
@ai_summary_access_required
@permission_required("view_reviews")
def get_summary(summary_id):
    return success_response(g.current_summary.to_dict())


@summaries_bp.route("/<summary_id>", methods=["PATCH"])
@ai_summary_access_required
@permission_required("generate_report")
def update_summary(summary_id):
    data = UpdateSummarySchema().load(request.get_json(force=True) or {})
    summary = ai_summary_service.update_summary(g.current_summary, data["sections"], g.current_user.id)
    return success_response(summary.to_dict(), message="Summary updated")


@summaries_bp.route("/<summary_id>/submit-for-review", methods=["POST"])
@ai_summary_access_required
@permission_required("generate_report")
def submit_for_review(summary_id):
    summary = ai_summary_service.submit_for_review(g.current_summary, g.current_user.id)
    return success_response(summary.to_dict(), message="Summary submitted for review")


@summaries_bp.route("/<summary_id>/approve", methods=["POST"])
@ai_summary_access_required
@permission_required("approve_ai_output")
def approve_summary(summary_id):
    data = ApproveSummarySchema().load(request.get_json(silent=True) or {})
    summary = ai_summary_service.approve_summary(
        g.current_summary, g.current_user.id, edited_sections=data.get("editedContent")
    )
    return success_response(summary.to_dict(), message="Summary approved")


@summaries_bp.route("/<summary_id>/reject", methods=["POST"])
@ai_summary_access_required
@permission_required("approve_ai_output")
def reject_summary(summary_id):
    data = RejectSummarySchema().load(request.get_json(silent=True) or {})
    summary = ai_summary_service.reject_summary(g.current_summary, g.current_user.id, data.get("reason"))
    return success_response(summary.to_dict(), message="Summary rejected")
