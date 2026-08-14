from app.extensions import db
from app.models import (
    Permission,
    PERMISSION_CATALOGUE,
    Role,
    BUILT_IN_ROLES,
    DEFAULT_ROLE_PERMISSIONS,
    RolePermission,
)


def seed_permissions_and_roles():
    """Idempotent seed of the fixed permission catalogue and the 6 built-in roles.

    Safe to call on every app startup / test setup — only inserts what's missing.
    """
    code_to_permission = {p.code: p for p in Permission.query.all()}
    for code, description in PERMISSION_CATALOGUE:
        if code not in code_to_permission:
            perm = Permission(code=code, description=description)
            db.session.add(perm)
            code_to_permission[code] = perm
    db.session.flush()

    name_to_role = {
        r.name: r for r in Role.query.filter(Role.organisation_id.is_(None)).all()
    }
    for role_name in BUILT_IN_ROLES:
        if role_name not in name_to_role:
            role = Role(organisation_id=None, name=role_name, is_custom=False)
            db.session.add(role)
            db.session.flush()
            name_to_role[role_name] = role

        role = name_to_role[role_name]
        existing_codes = {rp.permission.code for rp in role.role_permissions}
        for perm_code in DEFAULT_ROLE_PERMISSIONS.get(role_name, []):
            if perm_code not in existing_codes:
                db.session.add(
                    RolePermission(
                        role_id=role.id, permission_id=code_to_permission[perm_code].id
                    )
                )

    db.session.commit()


def get_built_in_role(name):
    return Role.query.filter_by(organisation_id=None, name=name).first()
