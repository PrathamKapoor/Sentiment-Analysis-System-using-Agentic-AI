# Phase 1 revocation store: in-memory jti blocklist.
# ponytail: single-process set, fine for dev/test/single-instance deploys.
# Swap for a Redis/DB-backed blocklist before running multiple app instances.
_revoked_jti = set()


def revoke_token(jti):
    _revoked_jti.add(jti)


def is_revoked(jti):
    return jti in _revoked_jti
