from flask import Blueprint, request, g

from app.extensions import db
from app.errors.exceptions import ValidationError, NotFoundError, ForbiddenError
from app.models import Organisation, OrganisationMember
from app.schemas.organisation_schemas import (
    UpdateOrganisationSchema, InviteMemberSchema, UpdateMemberSchema,
)
from app.decorators.auth import (
    jwt_required_custom, organisation_member_required, permission_required,
)
from app.services import organisation_service
from app.services.audit_service import log_action
from app.services.seed_service import get_built_in_role
from app.services.role_service import assign_role_to_member
from app.utils.responses import success_response

organisations_bp = Blueprint("organisations", __name__)


@organisations_bp.route("", methods=["POST"])
@jwt_required_custom
def create_organisation():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("name is required")

    owner_role = get_built_in_role("Organisation Owner")
    organisation = Organisation(name=name)
    db.session.add(organisation)
    db.session.flush()

    membership = OrganisationMember(
        organisation_id=organisation.id, user_id=g.current_user.id,
        status=OrganisationMember.STATUS_ACTIVE,
    )
    db.session.add(membership)
    db.session.flush()
    assign_role_to_member(membership, owner_role)

    log_action(organisation.id, g.current_user.id, "organisation.create", "organisation", organisation.id)
    db.session.commit()

    return success_response(organisation.to_dict(), message="Organisation created", status_code=201)


@organisations_bp.route("/<organisation_id>", methods=["GET"])
@organisation_member_required
def get_organisation(organisation_id):
    organisation = organisation_service.get_organisation_or_404(organisation_id)
    return success_response(organisation.to_dict())


@organisations_bp.route("/<organisation_id>", methods=["PATCH"])
@organisation_member_required
def update_organisation(organisation_id):
    membership = g.current_membership
    if not ({"Organisation Owner", "Organisation Administrator"} & set(membership.role_names())):
        raise ForbiddenError("Only the Owner or an Administrator can edit organisation details")

    data = UpdateOrganisationSchema().load(request.get_json(force=True) or {})
    if "plan" in data and "Organisation Owner" not in membership.role_names():
        raise ForbiddenError("Only the Owner can change the billing plan")

    organisation = organisation_service.get_organisation_or_404(organisation_id)
    organisation_service.update_organisation(organisation, data)
    log_action(organisation.id, g.current_user.id, "organisation.update", "organisation", organisation.id, data)
    db.session.commit()
    return success_response(organisation.to_dict(), message="Organisation updated")


@organisations_bp.route("/<organisation_id>/users", methods=["GET"])
@organisation_member_required
@permission_required("manage_users")
def list_users(organisation_id):
    members = organisation_service.list_members(organisation_id)
    return success_response({"items": [m.to_dict() for m in members]})


@organisations_bp.route("/<organisation_id>/users/invite", methods=["POST"])
@organisation_member_required
@permission_required("manage_users")
def invite_user(organisation_id):
    data = InviteMemberSchema().load(request.get_json(force=True) or {})
    membership = organisation_service.invite_member(organisation_id, data["email"])
    log_action(
        organisation_id, g.current_user.id, "user.invite", "organisation_member", membership.id,
        {"email": data["email"]},
    )
    db.session.commit()
    return success_response(membership.to_dict(), message="Invitation created", status_code=201)


@organisations_bp.route("/<organisation_id>/users/<user_id>", methods=["PATCH"])
@organisation_member_required
@permission_required("manage_users")
def update_user(organisation_id, user_id):
    data = UpdateMemberSchema().load(request.get_json(force=True) or {})
    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise NotFoundError("Member not found")
    organisation_service.update_member(membership, data)
    log_action(organisation_id, g.current_user.id, "user.update", "organisation_member", membership.id, data)
    db.session.commit()
    return success_response(membership.to_dict(), message="Member updated")


@organisations_bp.route("/<organisation_id>/users/<user_id>", methods=["DELETE"])
@organisation_member_required
@permission_required("manage_users")
def remove_user(organisation_id, user_id):
    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise NotFoundError("Member not found")
    organisation_service.remove_member(organisation_id, membership)
    log_action(organisation_id, g.current_user.id, "user.remove", "organisation_member", user_id)
    db.session.commit()
    return success_response(message="Member removed")
