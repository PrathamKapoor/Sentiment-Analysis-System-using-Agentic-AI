from datetime import datetime, timezone

from app.extensions import db
from app.errors.exceptions import NotFoundError, ConflictError
from app.models import Organisation, OrganisationMember, User


def get_organisation_or_404(organisation_id):
    org = Organisation.query.filter_by(id=organisation_id).filter(
        Organisation.deleted_at.is_(None)
    ).first()
    if org is None:
        raise NotFoundError("Organisation not found")
    return org


def update_organisation(organisation, data):
    if "name" in data:
        organisation.name = data["name"]
    if "plan" in data:
        organisation.plan = data["plan"]
    db.session.commit()
    return organisation


def list_members(organisation_id):
    return (
        OrganisationMember.query.filter_by(organisation_id=organisation_id)
        .join(User)
        .all()
    )


def invite_member(organisation_id, email, role_ids=None):
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if user is None:
        # Phase 1: create a placeholder user record awaiting acceptance.
        # No email is sent yet — this satisfies the "pending membership" requirement.
        user = User(email=email, name=email.split("@")[0])
        user.password_hash = "!invited"  # unusable hash; user sets a real password on acceptance
        db.session.add(user)
        db.session.flush()

    existing = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user.id
    ).first()
    if existing:
        raise ConflictError("User is already a member of this organisation")

    membership = OrganisationMember(
        organisation_id=organisation_id,
        user_id=user.id,
        status=OrganisationMember.STATUS_INVITED,
        invited_at=datetime.now(timezone.utc),
    )
    db.session.add(membership)
    db.session.commit()
    return membership


def update_member(membership, data):
    if "status" in data:
        membership.status = data["status"]
    db.session.commit()
    return membership


def remove_member(organisation_id, membership):
    from app.services.permission_service import is_owner

    if is_owner(membership):
        remaining_owners = [
            m for m in list_members(organisation_id)
            if m.id != membership.id and is_owner(m)
        ]
        if not remaining_owners:
            raise ConflictError("Cannot remove the organisation's last Owner")
    db.session.delete(membership)
    db.session.commit()
