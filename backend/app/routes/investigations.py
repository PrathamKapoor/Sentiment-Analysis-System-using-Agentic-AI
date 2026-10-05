from flask import Blueprint, g, request

from app.decorators.auth import permission_required, project_access_required
from app.errors.exceptions import ForbiddenError
from app.schemas.investigation_schemas import CreateInvestigationSchema, ReviewInvestigationFindingSchema
from app.services.permission_service import has_permission
from app.services import investigation_service
from app.utils.responses import success_response

project_investigations_bp = Blueprint("project_investigations", __name__)


@project_investigations_bp.route("", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def create_project_investigation(project_id):
    data = CreateInvestigationSchema().load(request.get_json(force=True) or {})
    row, created = investigation_service.create_investigation(
        g.current_project, g.current_user.id, g.current_membership,
        data["question"], data.get("idempotencyKey"),
    )
    return success_response(row.to_dict(), message="Investigation queued" if created else "Existing investigation returned",
                            status_code=202 if created else 200)


@project_investigations_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_project_investigations(project_id):
    try:
        limit = max(1, min(int(request.args.get("limit", 30)), 100))
    except (TypeError, ValueError):
        limit = 30
    return success_response({"items": [row.to_dict() for row in
        investigation_service.list_investigations(project_id, limit)]})


@project_investigations_bp.route("/<investigation_id>", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_project_investigation(project_id, investigation_id):
    row = investigation_service.get_investigation(project_id, g.current_organisation_id, investigation_id)
    return success_response(row.to_dict())


@project_investigations_bp.route("/<investigation_id>/cancel", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def cancel_project_investigation(project_id, investigation_id):
    row = investigation_service.get_investigation(project_id, g.current_organisation_id, investigation_id)
    if row.requested_by != g.current_user.id and not has_permission(g.current_membership, "edit_project"):
        raise ForbiddenError("Only the requester or a project editor can cancel this investigation")
    return success_response(investigation_service.cancel_investigation(row, g.current_user.id).to_dict(),
                            message="Investigation cancelled")


@project_investigations_bp.route("/<investigation_id>/findings/<finding_id>", methods=["PATCH"])
@project_access_required
@permission_required("approve_ai_output")
def review_project_investigation_finding(project_id, investigation_id, finding_id):
    row = investigation_service.get_investigation(project_id, g.current_organisation_id, investigation_id)
    data = ReviewInvestigationFindingSchema().load(request.get_json(force=True) or {})
    finding = investigation_service.review_finding(row, finding_id, g.current_user.id,
        data["status"], data.get("notes"))
    return success_response(finding.to_dict(), message="Investigation finding reviewed")
