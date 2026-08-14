from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.extensions import db
from app.errors.exceptions import EmailAlreadyRegisteredError, UnauthenticatedError
from app.models import Organisation, User, OrganisationMember, MemberRole
from app.services.seed_service import get_built_in_role
from app.services.audit_service import log_action


def register_organisation(organisation_name, email, password, name):
    """Create the first user + their organisation + Owner membership, in one transaction."""
    email = email.strip().lower()
    if _find_user_by_email_identity(email):
        raise EmailAlreadyRegisteredError()

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
    except IntegrityError as exc:
        db.session.rollback()
        # The unique index is the final guard against simultaneous requests.
        # Do not expose constraint/driver details to the public API.
        if _find_user_by_email_identity(email):
            raise EmailAlreadyRegisteredError() from exc
        raise
    except Exception:
        db.session.rollback()
        raise

    return organisation, user, membership


def authenticate(email, password):
    email = email.strip().lower()
    user = _find_user_by_email_identity(email)
    if user is None or user.is_deleted or not user.check_password(password):
        raise UnauthenticatedError("Invalid email or password")
    return user


def _find_user_by_email_identity(email):
    """Lookup is case/space-insensitive for legacy rows as well as new ones."""
    return User.query.filter(func.lower(func.trim(User.email)) == email).first()


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
