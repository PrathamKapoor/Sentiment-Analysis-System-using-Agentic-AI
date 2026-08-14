from app.models import OrganisationMember


def get_effective_permissions(membership: OrganisationMember):
    codes = set()
    for member_role in membership.member_roles:
        codes.update(member_role.role.permission_codes())
    return codes


def has_permission(membership: OrganisationMember, permission_code):
    return permission_code in get_effective_permissions(membership)


def is_owner(membership: OrganisationMember):
    return "Organisation Owner" in membership.role_names()
