from app.extensions import db
from app.errors.exceptions import NotFoundError, ConflictError, ValidationError
from app.models import Role, Permission, RolePermission, MemberRole, OrganisationMember


def list_roles(organisation_id):
    return Role.query.filter(
        (Role.organisation_id == organisation_id) | (Role.organisation_id.is_(None))
    ).all()


def get_role_or_404(role_id, organisation_id):
    role = Role.query.filter_by(id=role_id).first()
    if role is None:
        raise NotFoundError("Role not found")
    if role.organisation_id is not None and str(role.organisation_id) != str(organisation_id):
        raise NotFoundError("Role not found")
    return role


def create_custom_role(organisation_id, name, permission_codes=None):
    existing = Role.query.filter_by(organisation_id=organisation_id, name=name).first()
    if existing:
        raise ConflictError("A role with this name already exists in this organisation")

    role = Role(organisation_id=organisation_id, name=name, is_custom=True)
    db.session.add(role)
    db.session.flush()

    if permission_codes:
        _set_role_permissions(role, permission_codes)

    db.session.commit()
    return role


def update_role(role, data):
    if role.organisation_id is None:
        raise ValidationError("Built-in roles cannot be renamed")
    if "name" in data:
        role.name = data["name"]
    if "permissionCodes" in data:
        _set_role_permissions(role, data["permissionCodes"])
    db.session.commit()
    return role


def delete_role(role):
    if role.organisation_id is None:
        raise ValidationError("Built-in roles cannot be deleted")
    if role.name == "Organisation Owner":
        raise ValidationError("The Organisation Owner role cannot be deleted")
    in_use = MemberRole.query.filter_by(role_id=role.id).first()
    if in_use:
        raise ConflictError("Role is currently assigned to one or more members")
    db.session.delete(role)
    db.session.commit()


def _set_role_permissions(role, permission_codes):
    RolePermission.query.filter_by(role_id=role.id).delete()
    permissions = Permission.query.filter(Permission.code.in_(permission_codes)).all()
    found_codes = {p.code for p in permissions}
    missing = set(permission_codes) - found_codes
    if missing:
        raise ValidationError(f"Unknown permission code(s): {', '.join(sorted(missing))}")
    for perm in permissions:
        db.session.add(RolePermission(role_id=role.id, permission_id=perm.id))


def assign_role_to_member(membership: OrganisationMember, role: Role):
    if role.organisation_id is not None and str(role.organisation_id) != str(membership.organisation_id):
        raise ValidationError("Role does not belong to this organisation")
    existing = MemberRole.query.filter_by(
        organisation_member_id=membership.id, role_id=role.id
    ).first()
    if existing:
        raise ConflictError("Member already holds this role")
    db.session.add(MemberRole(organisation_member_id=membership.id, role_id=role.id))
    db.session.commit()


def remove_role_from_member(membership: OrganisationMember, role: Role):
    if role.name == "Organisation Owner":
        remaining = MemberRole.query.join(Role).filter(
            Role.name == "Organisation Owner",
            MemberRole.organisation_member_id != membership.id,
        ).first()
        if not remaining:
            raise ConflictError("Cannot remove the organisation's only Owner")
    link = MemberRole.query.filter_by(
        organisation_member_id=membership.id, role_id=role.id
    ).first()
    if link is None:
        raise NotFoundError("Member does not hold this role")
    db.session.delete(link)
    db.session.commit()
