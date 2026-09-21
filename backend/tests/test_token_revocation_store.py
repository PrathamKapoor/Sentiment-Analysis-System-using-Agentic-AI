"""Tests for the multi-instance token revocation store.

These tests cover the ``TokenRevocationStore`` abstraction:

  * InMemoryRevocationStore — default, single-process
  * RedisRevocationStore    — shared, multi-instance safe
  * factory + reset hook
  * fail-closed behavior on Redis outage
  * TTL computation

The Redis backend is exercised with a fake ``redis`` module installed
in ``sys.modules`` so the test does not need a real Redis instance.
"""
from __future__ import annotations

import os
import sys
import time
import types
from unittest import mock

import pytest

from app.services import token_service
from app.services.token_service import (
    InMemoryRevocationStore,
    RedisRevocationStore,
    get_revocation_store,
    is_revoked,
    reset_revocation_store,
    revoke_token,
)


@pytest.fixture(autouse=True)
def _reset_store():
    """Ensure each test starts with a clean module-scope store."""
    reset_revocation_store(None)
    yield
    reset_revocation_store(None)


# ---------- InMemoryRevocationStore ----------


def test_in_memory_revoke_and_check():
    s = InMemoryRevocationStore()
    assert s.is_revoked("jti-1") is False
    s.revoke("jti-1", exp_unix=time.time() + 60)
    assert s.is_revoked("jti-1") is True


def test_in_memory_does_not_share_between_instances():
    a = InMemoryRevocationStore()
    b = InMemoryRevocationStore()
    a.revoke("jti-shared", exp_unix=time.time() + 60)
    # b is a different process; it does not see the revocation.
    assert b.is_revoked("jti-shared") is False


# ---------- Factory ----------


def test_factory_returns_in_memory_by_default(monkeypatch):
    monkeypatch.delenv("REVOCATION_STORE_URL", raising=False)
    reset_revocation_store(None)
    store = get_revocation_store()
    assert isinstance(store, InMemoryRevocationStore)


def test_factory_rejects_unknown_scheme(monkeypatch):
    monkeypatch.setenv("REVOCATION_STORE_URL", "memcached://localhost:11211")
    with pytest.raises(RuntimeError, match="not a supported scheme"):
        get_revocation_store()


# ---------- RedisRevocationStore with fake redis ----------


class _FakeRedis:
    def __init__(self):
        self.store = {}  # key -> (value, expire_at)
        self.fail = False

    def set(self, key, value, ex=None):
        if self.fail:
            raise RuntimeError("simulated redis outage")
        self.store[key] = (value, time.time() + (ex or 0))

    def exists(self, key):
        if self.fail:
            raise RuntimeError("simulated redis outage")
        v = self.store.get(key)
        if not v:
            return False
        _, exp = v
        if exp and exp < time.time():
            self.store.pop(key, None)
            return False
        return True


@pytest.fixture
def fake_redis_module(monkeypatch):
    fake = types.ModuleType("redis")

    def _factory(*a, **kw):
        return _FakeRedis()

    class _Redis:
        @staticmethod
        def from_url(url, **kw):
            return _factory(url, **kw)

    fake.Redis = _Redis
    monkeypatch.setitem(sys.modules, "redis", fake)
    yield fake


def test_redis_revoke_and_check(fake_redis_module):
    s = RedisRevocationStore(redis_url="redis://localhost:6379/0")
    assert s.is_revoked("jti-r-1") is False
    s.revoke("jti-r-1", exp_unix=time.time() + 60)
    assert s.is_revoked("jti-r-1") is True


def test_redis_fail_closed_on_read_outage(fake_redis_module):
    s = RedisRevocationStore(redis_url="redis://localhost:6379/0")
    # Manually swap in a redis client that always fails.
    s._client = _FakeRedis()
    s._client.fail = True
    # Read outage must return True (fail-closed) so revoked tokens
    # are not silently accepted.
    assert s.is_revoked("anything") is True


def test_redis_propagates_write_failures(fake_redis_module):
    s = RedisRevocationStore(redis_url="redis://localhost:6379/0")
    s._client = _FakeRedis()
    s._client.fail = True
    with pytest.raises(RuntimeError, match="simulated redis outage"):
        s.revoke("jti-write", exp_unix=time.time() + 60)


def test_redis_ttl_matches_token_expiry(fake_redis_module):
    s = RedisRevocationStore(redis_url="redis://localhost:6379/0")
    future = time.time() + 120
    s.revoke("jti-ttl", exp_unix=future)
    # The stored TTL should be ~120 (allow a small scheduling slack).
    # We verify by reading the underlying store: a key that would
    # have expired by now is not present.
    assert s.is_revoked("jti-ttl") is True
    # Manually expire the key by rewinding time: simulate by clearing
    # the store and verifying re-add with very short TTL.
    s._client = _FakeRedis()
    s.revoke("jti-ttl-soon", exp_unix=time.time() - 1)
    # Token has already expired: key gets 60s fallback so it is still
    # present for in-flight requests.
    assert s.is_revoked("jti-ttl-soon") is True

    assert RedisRevocationStore._compute_ttl(None) == 24 * 60 * 60
    assert RedisRevocationStore._compute_ttl("not-a-number") == 24 * 60 * 60
    future = time.time() + 120
    assert RedisRevocationStore._compute_ttl(future) in (119, 120)

def test_factory_returns_redis_when_configured(fake_redis_module, monkeypatch):
    monkeypatch.setenv("REVOCATION_STORE_URL", "redis://localhost:6379/0")
    reset_revocation_store(None)
    store = get_revocation_store()
    assert isinstance(store, RedisRevocationStore)


def test_module_level_revoke_routes_to_active_store():
    """``revoke_token`` and ``is_revoked`` (the names imported by
    the routes and the blocklist callback) must use the active
    store."""
    fake = InMemoryRevocationStore()
    reset_revocation_store(fake)
    revoke_token("jti-public", exp_unix=time.time() + 60)
    assert is_revoked("jti-public") is True
    assert is_revoked("jti-other") is False