from flask import Blueprint, request, g

from app.schemas.alert_schemas import (
    CreateAlertSchema, UpdateAlertSchema, AssignAlertSchema, ResolveAlertSchema,
)
from app.decorators.auth import project_access_required, permission_required, alert_access_required
from app.services import alert_service
from app.errors.exceptions import ForbiddenError
from app.services.permission_service import has_permission
from app.utils.responses import success_response

project_alerts_bp = Blueprint("project_alerts", __name__)
alerts_bp = Blueprint("alerts", __name__)


@project_alerts_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_alerts(project_id):
    filters = {
        "status": request.args.get("status"),
        "priority": request.args.get("priority"),
    }
    items = alert_service.list_alerts(project_id, filters)
    return success_response({"items": [a.to_dict() for a in items]})


@project_alerts_bp.route("", methods=["POST"])
@project_access_required
@permission_required("manage_alerts")
def create_alert(project_id):
    data = CreateAlertSchema().load(request.get_json(force=True) or {})
    alert = alert_service.create_alert(project_id, g.current_user.id, data)
    return success_response(alert.to_dict(), message="Alert rule created", status_code=201)


@project_alerts_bp.route("/evaluate", methods=["POST"])
@project_access_required
@permission_required("manage_alerts")
def evaluate_project_alerts(project_id):
    results = alert_service.evaluate_project_alerts(project_id, g.current_user.id)
    return success_response({"items": results})


@alerts_bp.route("/<alert_id>", methods=["GET"])
@alert_access_required
@permission_required("view_reviews")
def get_alert(alert_id):
    return success_response(g.current_alert.to_dict())


@alerts_bp.route("/<alert_id>", methods=["PATCH"])
@alert_access_required
@permission_required("manage_alerts")
def update_alert(alert_id):
    data = UpdateAlertSchema().load(request.get_json(force=True) or {})
    alert = alert_service.update_alert(g.current_alert, data, g.current_user.id)
    return success_response(alert.to_dict(), message="Alert rule updated")


@alerts_bp.route("/<alert_id>", methods=["DELETE"])
@alert_access_required
@permission_required("manage_alerts")
def delete_alert(alert_id):
    alert_service.delete_alert(g.current_alert, g.current_user.id)
    return success_response(message="Alert rule deleted")


@alerts_bp.route("/<alert_id>/enable", methods=["POST"])
@alert_access_required
@permission_required("manage_alerts")
def enable_alert(alert_id):
    alert = alert_service.set_enabled(g.current_alert, True, g.current_user.id)
    return success_response(alert.to_dict(), message="Alert rule enabled")


@alerts_bp.route("/<alert_id>/disable", methods=["POST"])
@alert_access_required
@permission_required("manage_alerts")
def disable_alert(alert_id):
    alert = alert_service.set_enabled(g.current_alert, False, g.current_user.id)
    return success_response(alert.to_dict(), message="Alert rule disabled")


@alerts_bp.route("/<alert_id>/evaluate", methods=["POST"])
@alert_access_required
@permission_required("manage_alerts")
def evaluate_alert(alert_id):
    result = alert_service.evaluate_alert(g.current_alert, g.current_user.id)
    return success_response({"alert": g.current_alert.to_dict(), **result})


@alerts_bp.route("/<alert_id>/acknowledge", methods=["POST"])
@alert_access_required
def acknowledge_alert(alert_id):
    _require_manage_or_assignee()
    alert = alert_service.acknowledge_alert(g.current_alert, g.current_user.id)
    return success_response(alert.to_dict(), message="Alert acknowledged")


@alerts_bp.route("/<alert_id>/assign", methods=["POST"])
@alert_access_required
@permission_required("manage_alerts")
def assign_alert(alert_id):
    data = AssignAlertSchema().load(request.get_json(force=True) or {})
    alert = alert_service.assign_alert(g.current_alert, data["userId"], g.current_user.id)
    return success_response(alert.to_dict(), message="Alert assigned")


@alerts_bp.route("/<alert_id>/resolve", methods=["POST"])
@alert_access_required
def resolve_alert(alert_id):
    _require_manage_or_assignee()
    data = ResolveAlertSchema().load(request.get_json(force=True) or {})
    alert = alert_service.resolve_alert(g.current_alert, data["resolutionNotes"], g.current_user.id)
    return success_response(alert.to_dict(), message="Alert resolved")


def _require_manage_or_assignee():
    # Per the approved REST API Spec: "manage_alerts or assignee".
    is_assignee = (
        g.current_alert.assigned_to is not None
        and str(g.current_alert.assigned_to) == str(g.current_user.id)
    )
    if not is_assignee and not has_permission(g.current_membership, "manage_alerts"):
        raise ForbiddenError("Only the assignee or a user with manage_alerts may perform this action")
