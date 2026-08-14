from flask import Blueprint, request, g

from app.extensions import db
from app.models import OrganisationMember
from app.schemas.role_schemas import CreateRoleSchema, UpdateRoleSchema
from app.decorators.auth import organisation_member_required, permission_required
from app.services import role_service
from app.services.audit_service import log_action
from app.errors.exceptions import NotFoundError
from app.utils.responses import success_response

roles_bp = Blueprint("roles", __name__)


@roles_bp.route("", methods=["GET"])
@organisation_member_required
def list_roles(organisation_id):
    roles = role_service.list_roles(organisation_id)
    return success_response({"items": [r.to_dict() for r in roles]})


@roles_bp.route("", methods=["POST"])
@organisation_member_required
@permission_required("manage_roles")
def create_role(organisation_id):
    data = CreateRoleSchema().load(request.get_json(force=True) or {})
    role = role_service.create_custom_role(organisation_id, data["name"], data.get("permissionCodes"))
    log_action(organisation_id, g.current_user.id, "role.create", "role", role.id, {"name": role.name})
    db.session.commit()
    return success_response(role.to_dict(), message="Role created", status_code=201)


@roles_bp.route("/<role_id>", methods=["PATCH"])
@organisation_member_required
@permission_required("manage_roles")
def update_role(organisation_id, role_id):
    data = UpdateRoleSchema().load(request.get_json(force=True) or {})
    role = role_service.get_role_or_404(role_id, organisation_id)
    role_service.update_role(role, data)
    log_action(organisation_id, g.current_user.id, "role.update", "role", role.id, data)
    db.session.commit()
    return success_response(role.to_dict(), message="Role updated")


@roles_bp.route("/<role_id>", methods=["DELETE"])
@organisation_member_required
@permission_required("manage_roles")
def delete_role(organisation_id, role_id):
    role = role_service.get_role_or_404(role_id, organisation_id)
    role_service.delete_role(role)
    log_action(organisation_id, g.current_user.id, "role.delete", "role", role_id)
    db.session.commit()
    return success_response(message="Role deleted")


@roles_bp.route("/<role_id>/assign", methods=["POST"])
@organisation_member_required
@permission_required("manage_roles")
def assign_role(organisation_id, role_id):
    data = request.get_json(force=True) or {}
    user_id = data.get("userId")
    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise NotFoundError("Member not found")
    role = role_service.get_role_or_404(role_id, organisation_id)
    role_service.assign_role_to_member(membership, role)
    log_action(organisation_id, g.current_user.id, "role.assign", "member_role", membership.id, {"role": role.name})
    db.session.commit()
    return success_response(membership.to_dict(), message="Role assigned")


@roles_bp.route("/<role_id>/unassign", methods=["POST"])
@organisation_member_required
@permission_required("manage_roles")
def unassign_role(organisation_id, role_id):
    data = request.get_json(force=True) or {}
    user_id = data.get("userId")
    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise NotFoundError("Member not found")
    role = role_service.get_role_or_404(role_id, organisation_id)
    role_service.remove_role_from_member(membership, role)
    log_action(organisation_id, g.current_user.id, "role.unassign", "member_role", membership.id, {"role": role.name})
    db.session.commit()
    return success_response(membership.to_dict(), message="Role removed")
