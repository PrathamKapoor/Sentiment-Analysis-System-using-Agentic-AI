from datetime import datetime, timezone

from app.extensions import db
from app.errors.exceptions import ConflictError, UnauthenticatedError
from app.models import Organisation, User, OrganisationMember, MemberRole
from app.services.seed_service import get_built_in_role
from app.services.audit_service import log_action


def register_organisation(organisation_name, email, password, name):
    """Create the first user + their organisation + Owner membership, in one transaction."""
    email = email.strip().lower()
    if User.query.filter_by(email=email).first():
        raise ConflictError("Email already registered")

    owner_role = get_built_in_role("Organisation Owner")
    if owner_role is None:
        raise RuntimeError("Roles have not been seeded — run seed_permissions_and_roles()")

    try:
        organisation = Organisation(name=organisation_name)
        db.session.add(organisation)
        db.session.flush()

        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        now = datetime.now(timezone.utc)
        membership = OrganisationMember(
            organisation_id=organisation.id,
            user_id=user.id,
            status=OrganisationMember.STATUS_ACTIVE,
            joined_at=now,
        )
        db.session.add(membership)
        db.session.flush()

        db.session.add(MemberRole(organisation_member_id=membership.id, role_id=owner_role.id))

        log_action(
            organisation.id, user.id, "organisation.register", "organisation", organisation.id,
            {"email": email},
        )

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return organisation, user, membership


def authenticate(email, password):
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if user is None or user.is_deleted or not user.check_password(password):
        raise UnauthenticatedError("Invalid email or password")
    return user


def get_user_organisations(user):
    memberships = (
        OrganisationMember.query.filter_by(user_id=user.id)
        .filter(OrganisationMember.status == OrganisationMember.STATUS_ACTIVE)
        .all()
    )
    result = []
    for m in memberships:
        result.append({
            "organisationId": str(m.organisation_id),
            "organisationName": m.organisation.name,
            "membershipId": str(m.id),
            "roles": m.role_names(),
        })
    return result
