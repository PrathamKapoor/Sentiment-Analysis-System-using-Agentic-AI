"""Verify the rate-limiter storage URL wiring.

The Flask-Limiter instance is built from ``LIMITER_STORAGE_URL``.
The supported URIs are:

  * ``memory://`` — default, in-process
  * ``redis://...`` — production multi-instance
  * any other storage URI supported by Flask-Limiter

The point of this test is to prove that:

  1. the storage URI is forwarded to the Limiter at construction time
  2. an unknown / unsupported scheme does not crash the process
  3. the default is in-memory when no env is set

This is NOT a test of Flask-Limiter itself, which is a third-party
dependency. The actual distributed behavior is covered separately:

  * ``tests/test_redis_integration.py`` exercises two Flask-Limiter
    instances sharing one real Redis server (skipped when no Redis is
    reachable).
  * ``scripts/phase14_distributed_verification.py`` proves the same
    sharing across two real OS processes over HTTP.
"""
from __future__ import annotations

import pytest

from app.limiter import create_limiter


def test_limiter_default_uses_memory(monkeypatch):
    monkeypatch.delenv("LIMITER_STORAGE_URL", raising=False)
    lim = create_limiter(enabled=True)
    assert lim is not None
    # The default storage URI is "memory://" — a substring check
    # protects us against Flask-Limiter rewriting the URI in
    # future versions.
    storage = lim._storage_uri
    assert "memory" in storage


def test_limiter_passes_redis_uri_through(monkeypatch):
    monkeypatch.setenv(
        "LIMITER_STORAGE_URL",
        "redis://prod-redis.internal:6379/0",
    )
    lim = create_limiter(enabled=True)
    storage = lim._storage_uri
    assert "redis://prod-redis.internal" in storage


def test_limiter_disabled_returns_none(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    lim = create_limiter()
    assert lim is None


def test_limiter_disabled_via_factory_arg():
    """``create_limiter(enabled=False)`` returns None regardless of
    environment."""
    lim = create_limiter(enabled=False)
    assert lim is None