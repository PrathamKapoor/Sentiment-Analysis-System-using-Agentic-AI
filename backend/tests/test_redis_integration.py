"""Real-Redis integration tests for multi-instance production state.

These tests exercise the *actual* Redis server on localhost against:

  1. ``RedisRevocationStore`` — two independent store instances (the
     situation in two gunicorn workers / two replicas) must observe
     each other's revocations, and keys must expire with the token.

  2. Flask-Limiter with ``LIMITER_STORAGE_URL=redis://...`` — two
     independent ``Limiter`` instances backed by the same Redis must
     share one accounting bucket, which is the whole point of the
     shared store in a multi-instance deployment.

Isolation & safety:

  * Only dedicated logical databases (13 and 14) are used, never the
    default DB 0. Each test class flushes ONLY its own logical DB
    before and after itself.
  * The module skips cleanly when no Redis is reachable, so CI and
    single-process workstations without Redis keep working.

The two-*process* (real HTTP Gunicorn/waitress) proof lives in
``scripts/phase14_distributed_verification.py``; this module covers
the same semantics at the pytest level.
"""
from __future__ import annotations

import time

import pytest

REDIS_HOST_URL = "redis://localhost:6379"
REVOCATION_DB = 14
LIMITER_DB = 13


def _redis_available() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(
            f"{REDIS_HOST_URL}/{REVOCATION_DB}", socket_timeout=1
        )
        return bool(client.ping())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="no Redis server reachable on localhost:6379",
)


def _client(db: int):
    import redis

    return redis.Redis.from_url(
        f"{REDIS_HOST_URL}/{db}", decode_responses=True, socket_timeout=2
    )


@pytest.fixture
def revocation_db():
    client = _client(REVOCATION_DB)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def limiter_db():
    client = _client(LIMITER_DB)
    client.flushdb()
    yield client
    client.flushdb()


# ---------------------------------------------------------------------
# Revocation store against real Redis
# ---------------------------------------------------------------------


class TestRedisRevocationStoreRealRedis:
    def test_revocation_is_visible_across_store_instances(self, revocation_db):
        """Store instance A revokes; a *different* store instance B
        (a second worker/replica) must observe the revocation."""
        from app.services.token_service import RedisRevocationStore

        url = f"{REDIS_HOST_URL}/{REVOCATION_DB}"
        store_a = RedisRevocationStore(redis_url=url)
        store_b = RedisRevocationStore(redis_url=url)

        assert store_b.is_revoked("jti-cross-instance") is False
        store_a.revoke("jti-cross-instance", exp_unix=time.time() + 120)
        assert store_b.is_revoked("jti-cross-instance") is True

    def test_revocation_key_is_namespaced_and_ttl_bounded(self, revocation_db):
        """The Redis key must live under the configured prefix and its
        TTL must be <= the token's remaining lifetime (never permanent).
        """
        from app.services.token_service import RedisRevocationStore

        url = f"{REDIS_HOST_URL}/{REVOCATION_DB}"
        store = RedisRevocationStore(redis_url=url)
        exp = time.time() + 300
        store.revoke("jti-ttl-check", exp_unix=exp)

        key = f"{RedisRevocationStore.DEFAULT_KEY_PREFIX}jti-ttl-check"
        assert revocation_db.exists(key) == 1
        ttl = revocation_db.ttl(key)
        # TTL <= remaining lifetime, and obviously positive.
        assert 0 < ttl <= 300

    def test_revocation_expires_with_token(self, revocation_db):
        """A revoked JTI must disappear from Redis once the token
        itself would have expired — the store must not be permanent."""
        from app.services.token_service import RedisRevocationStore

        url = f"{REDIS_HOST_URL}/{REVOCATION_DB}"
        store = RedisRevocationStore(redis_url=url)
        # NB: _compute_ttl truncates to whole seconds, and sub-second
        # remainders fall into the documented 60s short-key clamp, so
        # this test uses a 2s horizon where the truncation can only
        # produce a TTL of 1s or 2s — both expire within the sleep.
        store.revoke("jti-short-lived", exp_unix=time.time() + 2)
        assert store.is_revoked("jti-short-lived") is True
        # Redis expires the key on its own; wait past the TTL.
        time.sleep(2.8)
        assert store.is_revoked("jti-short-lived") is False

    def test_revocation_survives_fresh_client(self, revocation_db):
        """Restart semantics: a brand-new client connection (what a
        restarted/redeployed instance gets) still sees the revocation."""
        from app.services.token_service import RedisRevocationStore

        url = f"{REDIS_HOST_URL}/{REVOCATION_DB}"
        store_a = RedisRevocationStore(redis_url=url)
        store_a.revoke("jti-restart", exp_unix=time.time() + 120)

        # Simulate process restart: drop every reference, build a new
        # store (new TCP connection) and re-check.
        del store_a
        store_b = RedisRevocationStore(redis_url=url)
        assert store_b.is_revoked("jti-restart") is True


# ---------------------------------------------------------------------
# Flask-Limiter shared accounting against real Redis
# ---------------------------------------------------------------------


class TestSharedRateLimitRealRedis:
    def test_two_limiter_instances_share_one_budget(self, limiter_db):
        """Instance A consumes part of the budget; instance B must see
        the remaining budget as already spent and a further request
        must be rejected with 429 on EITHER instance."""
        from flask import Flask
        from flask_limiter import Limiter

        storage_uri = f"{REDIS_HOST_URL}/{LIMITER_DB}"

        def build():
            app = Flask(__name__)
            app.config["TESTING"] = True
            limiter = Limiter(
                key_func=lambda: "shared-test-client",
                storage_uri=storage_uri,
                default_limits=[],
                headers_enabled=False,
            )
            limiter.init_app(app)

            @app.route("/hit")
            @limiter.limit("3 per 30 seconds")
            def hit():
                return "ok"

            return app

        app_a = build()
        app_b = build()
        client_a = app_a.test_client()
        client_b = app_b.test_client()

        # Instance A consumes the entire budget (3 per 30s).
        for _ in range(3):
            assert client_a.get("/hit").status_code == 200

        # The SAME budget must now be exhausted as seen from instance B
        # — no fresh 3-request allowance may appear there.
        assert client_b.get("/hit").status_code == 429

        # And instance A agrees the bucket is empty as well.
        assert client_a.get("/hit").status_code == 429
