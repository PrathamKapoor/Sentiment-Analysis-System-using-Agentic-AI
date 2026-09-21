"""Token revocation store.

The Flask-JWT-Extended ``token_in_blocklist_loader`` callback asks
``is_revoked(jti)`` for every protected request. The store therefore
must be:

  * fast (a Redis GET is acceptable; an HTTP call is not)
  * TTL-aware (no permanent keys; the key expires no later than the
    token itself would)
  * fail-safe (an outage in the configured production backend MUST
    not silently accept revoked tokens)

Backend choice
--------------

* ``InMemoryRevocationStore`` — default. Suitable for development,
  test, and single-process deployments. State is lost on restart,
  which is the documented limitation of a single-instance deployment.

* ``RedisRevocationStore`` — selected when ``REVOCATION_STORE_URL``
  starts with ``redis://`` or ``rediss://``. Suitable for production
  multi-instance deployments. Requires the optional ``redis`` Python
  package.

The active store is resolved at process start by
``get_revocation_store()`` from the environment. The store is cached
on the module so subsequent calls do not re-create the client.

TTL behavior
------------

The Redis key is stored with an EXPIRE matching the remaining token
lifetime (``exp - now``). When the token would naturally expire, the
revocation key disappears with it, so the set cannot grow without
bound. If the JWT is malformed or has no ``exp`` claim, the store
falls back to a conservative 24-hour TTL.

Failure behavior
----------------

If the configured production backend (``REVOCATION_STORE_URL=redis://``)
is configured but ``redis`` is not installed, the process fails to
boot. If Redis is configured but the connection fails on first use,
``is_revoked`` treats the token as revoked (``True``) so the worst
case is a forced re-authentication rather than a privilege retention.

Development fallback
--------------------

If ``REVOCATION_STORE_URL`` is not set, the in-memory store is used
regardless of environment. This keeps tests, demos, and single-host
deployments dependency-free.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class TokenRevocationStore(Protocol):
    """Interface for a token revocation store."""

    def revoke(self, jti: str, exp_unix: float | None = None) -> None:
        """Mark the JTI as revoked. ``exp_unix`` is the JWT exp claim
        (seconds since epoch) used to compute the storage TTL. If
        absent, the store uses a conservative fallback TTL."""

    def is_revoked(self, jti: str) -> bool:
        """Return True if the JTI has been revoked and is not yet
        naturally expired. Used by the blocklist callback on every
        protected request."""


class InMemoryRevocationStore:
    """In-process revocation set. Not multi-instance safe. Used for
    dev, test, and single-instance deployments."""

    def __init__(self) -> None:
        # jti -> exp_unix (used only for self-cleanup, which is not
        # possible in a single process anyway, but keeps the contract
        # consistent with the Redis backend).
        self._revoked: dict[str, float] = {}

    def revoke(self, jti: str, exp_unix: float | None = None) -> None:
        self._revoked[jti] = float(exp_unix) if exp_unix else 0.0

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked


class RedisRevocationStore:
    """Redis-backed revocation store. Multi-instance safe.

    Configuration is read from the ``redis_url`` argument. The
    optional ``key_prefix`` allows multiple deployments to share a
    Redis without colliding (default ``"sams:revoked:"``).

    On every ``is_revoked`` call, the store performs ``GET key``; if
    Redis is unreachable, the store returns ``True`` (fail-closed)
    and logs the failure. This means an outage forces every protected
    request to re-authenticate, which is the safe direction.
    """

    DEFAULT_KEY_PREFIX = "sams:revoked:"
    DEFAULT_FALLBACK_TTL_SECONDS = 24 * 60 * 60

    def __init__(self, redis_url: str, key_prefix: str = DEFAULT_KEY_PREFIX):
        # Verify the redis package is available at construction time
        # so a misconfigured production deployment fails at boot,
        # not at first authenticated request.
        try:
            import redis  # noqa: F401  (presence check)
        except ImportError as exc:
            raise RuntimeError(
                "REVOCATION_STORE_URL=redis://... requires the optional "
                "redis package. Install it (pip install redis) or "
                "unset REVOCATION_STORE_URL to use the in-memory store."
            ) from exc
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._client = None  # lazy

    def _key(self, jti: str) -> str:
        return f"{self._key_prefix}{jti}"

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        import redis
        self._client = redis.Redis.from_url(
            self._redis_url, decode_responses=True
        )
        return self._client

    def revoke(self, jti: str, exp_unix: float | None = None) -> None:
        client = self._ensure_client()
        ttl = self._compute_ttl(exp_unix)
        try:
            client.set(self._key(jti), "1", ex=ttl)
        except Exception as exc:
            logger.error(
                "revocation store set failed for jti=%s: %s", jti, exc
            )
            # Fail-closed: a write that we cannot confirm is treated
            # as if it never happened, so the user must re-auth.
            raise

    def is_revoked(self, jti: str) -> bool:
        client = self._ensure_client()
        try:
            return bool(client.exists(self._key(jti)))
        except Exception as exc:
            logger.error(
                "revocation store read failed for jti=%s: %s; "
                "treating as revoked (fail-closed)", jti, exc,
            )
            return True

    @staticmethod
    def _compute_ttl(exp_unix: float | None) -> int:
        """Return a sane TTL in seconds for the revocation key."""
        if exp_unix is None:
            return RedisRevocationStore.DEFAULT_FALLBACK_TTL_SECONDS
        try:
            exp_value = float(exp_unix)
        except (TypeError, ValueError):
            return RedisRevocationStore.DEFAULT_FALLBACK_TTL_SECONDS
        remaining = int(exp_value - time.time())
        if remaining <= 0:
            # Already expired; the token would have been rejected by
            # JWT validation anyway, but store a short key so the
            # set still records the fact for any in-flight request.
            return 60
        return remaining


_store: TokenRevocationStore | None = None
_store_kind: str = "unset"


def _build_default_store() -> TokenRevocationStore:
    """Resolve the active store from environment variables."""
    url = (os.environ.get("REVOCATION_STORE_URL") or "").strip()
    if not url:
        return InMemoryRevocationStore()
    if url.startswith("redis://") or url.startswith("rediss://"):
        prefix = os.environ.get("REVOCATION_STORE_PREFIX", "sams:revoked:")
        return RedisRevocationStore(redis_url=url, key_prefix=prefix)
    # Unknown scheme — refuse to silently fall back. The process
    # must not start with a misconfigured store.
    raise RuntimeError(
        f"REVOCATION_STORE_URL={url!r} is not a supported scheme. "
        "Use redis://.../rediss://... or leave unset for the in-memory store."
    )


def get_revocation_store() -> TokenRevocationStore:
    """Return the active revocation store, building it on first use.

    The result is cached in module scope. Tests that need to inject a
    store can call ``reset_revocation_store()`` first.
    """
    global _store, _store_kind
    if _store is None:
        _store = _build_default_store()
        _store_kind = type(_store).__name__
        logger.info("token revocation store: %s", _store_kind)
    return _store


def reset_revocation_store(store: TokenRevocationStore | None = None) -> None:
    """Tests swap the active store via this hook."""
    global _store, _store_kind
    _store = store
    _store_kind = type(store).__name__ if store is not None else "unset"


def revoke_token(jti: str, exp_unix: float | None = None) -> None:
    """Mark a JTI as revoked. Used by the logout and refresh routes."""
    get_revocation_store().revoke(jti, exp_unix)


def is_revoked(jti: str) -> bool:
    """Blocklist callback. Called on every protected request."""
    return get_revocation_store().is_revoked(jti)