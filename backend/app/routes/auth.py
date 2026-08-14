from flask import Blueprint, request, g
from flask_jwt_extended import (
    create_access_token, create_refresh_token, get_jwt, jwt_required,
)

from app.schemas.auth_schemas import RegisterSchema, LoginSchema
from app.services.auth_service import register_organisation, authenticate, get_user_organisations
from app.services.permission_service import get_effective_permissions
from app.services.token_service import revoke_token
from app.decorators.auth import jwt_required_custom
from app.utils.responses import success_response

auth_bp = Blueprint("auth", __name__)


def _issue_tokens(user_id):
    access_token = create_access_token(identity=str(user_id))
    refresh_token = create_refresh_token(identity=str(user_id))
    return access_token, refresh_token


@auth_bp.route("/register", methods=["POST"])
def register():
    data = RegisterSchema().load(request.get_json(force=True) or {})
    organisation, user, membership = register_organisation(
        data["organisationName"], data["email"], data["password"], data["name"]
    )
    access_token, refresh_token = _issue_tokens(user.id)
    return success_response(
        {
            "organisationId": str(organisation.id),
            "userId": str(user.id),
            "accessToken": access_token,
            "refreshToken": refresh_token,
        },
        message="Organisation registered successfully",
        status_code=201,
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    data = LoginSchema().load(request.get_json(force=True) or {})
    user = authenticate(data["email"], data["password"])
    access_token, refresh_token = _issue_tokens(user.id)
    organisations = get_user_organisations(user)
    active_org = organisations[0] if organisations else None

    permissions = []
    if active_org:
        from app.models import OrganisationMember
        membership = OrganisationMember.query.filter_by(
            organisation_id=active_org["organisationId"], user_id=user.id
        ).first()
        if membership:
            permissions = sorted(get_effective_permissions(membership))

    return success_response({
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "user": user.to_dict(),
        "organisations": organisations,
        "activeOrganisation": active_org,
        "roles": active_org["roles"] if active_org else [],
        "permissions": permissions,
    }, message="Login successful")


@auth_bp.route("/logout", methods=["POST"])
@jwt_required(verify_type=False)
def logout():
    jti = get_jwt()["jti"]
    revoke_token(jti)
    return success_response(message="Logged out successfully")


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    from flask_jwt_extended import get_jwt_identity

    old_jti = get_jwt()["jti"]
    revoke_token(old_jti)  # rotation: old refresh token is single-use

    identity = get_jwt_identity()
    access_token, refresh_token = _issue_tokens(identity)
    return success_response({
        "accessToken": access_token,
        "refreshToken": refresh_token,
    }, message="Token refreshed")


@auth_bp.route("/me", methods=["GET"])
@jwt_required_custom
def me():
    user = g.current_user
    organisations = get_user_organisations(user)
    requested_org_id = request.headers.get("X-Organisation-Id")
    active_org = next(
        (org for org in organisations if org["organisationId"] == requested_org_id),
        organisations[0] if organisations else None,
    )
    permissions = []
    if active_org:
        from app.models import OrganisationMember
        membership = OrganisationMember.query.filter_by(
            organisation_id=active_org["organisationId"], user_id=user.id
        ).first()
        if membership:
            permissions = sorted(get_effective_permissions(membership))
    return success_response({
        "user": user.to_dict(),
        "organisations": organisations,
        "activeOrganisation": active_org,
        "roles": active_org["roles"] if active_org else [],
        "permissions": permissions,
    })
