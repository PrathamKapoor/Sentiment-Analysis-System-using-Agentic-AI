"""Rate limiting — a single place to configure who is throttled and how.

Default limits are generous because the app is a small-team internal
tool, not a public API. The limiter is deliberately NOT applied to read
endpoints; calling analyse/regenerate for already-paid work is the
primary write path.

Chosen limits are tuned for cost-bearing endpoints:

- login/register: low (brute-force resistance)
- LLM/report generation: tighter than CRUD because each call may cost
  real money / CPU.
- website context refresh: bounded because an external fetch is being
  performed with our user agent.

The limiter is keyed by the authenticated user id when the caller is
logged in, falling back to client IP. This avoids the proxy-header
spoofing problem while still protecting unauthenticated login.

The underlying store is operations-local by default (``memory://``).
Setting ``LIMITER_STORAGE_URL=redis://...`` switches to a shared store,
which matters when the app runs multiple worker processes. A deployment
with a single process needs no Redis.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional


def _client_key():
    """Return a client identifier for rate limiting.

    Prefers the authenticated user id (stable, can't be faked by
    another proxy hop) and falls back to the client IP.
    """
    from flask import g, request
    user = getattr(g, "current_user", None)
    if user is not None and getattr(user, "id", None):
        return f"user:{user.id}"
    return request.remote_addr or "unknown"


def create_limiter(enabled: Optional[bool] = None):
    """Instantiate the shared Flask-Limiter extension. The app factory
    in ``app/__init__.py`` calls this once. Tests pass
    ``RATE_LIMIT_ENABLED=False`` through the app config so the test
    suite is deterministic.
    """
    from flask_limiter import Limiter

    if enabled is None:
        enabled = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
    if not enabled:
        return None

    # Default limits are intentionally NOT applied to every route. Health
    # endpoints must NEVER be rate-limited — orchestrators and load
    # balancers poll them multiple times per second and a 429 there would
    # cause the instance to be marked unhealthy and rotated out. The
    # ``apply_limits`` function below binds specific specs to the routes
    # that need protection (auth, expensive writes).
    default_limits = []
    storage_backend = os.environ.get("LIMITER_STORAGE_URL", "memory://")

    limiter = Limiter(
        key_func=_client_key,
        default_limits=default_limits,
        storage_uri=storage_backend,
        headers_enabled=False,
    )
    logging.getLogger(__name__).info(
        "rate limiting enabled (storage=%s)", storage_backend,
    )
    return limiter


def limit(spec: str) -> Callable:
    """Apply a per-route Flask-Limiter spec.

    The window and cost are interpreted by Flask-Limiter; the spec string
    documents intent. If the app has no limiter attached — tests,
    in-process embedding, or RATE_LIMIT_ENABLED=false — the wrapper
    passes through unchanged.
    """

    def decorator(fn):
        def wrapper(*args, **kwargs):
            from flask import current_app
            from flask_limiter import RateLimitExceeded

            ext = getattr(current_app, "extensions", {})
            entry = ext.get("limiter")
            candidate = None
            if isinstance(entry, set) and entry:
                candidate = next(iter(entry))
            elif entry is not None and hasattr(entry, "limit"):
                candidate = entry
            if candidate is None:
                return fn(*args, **kwargs)
            return candidate.limit(spec)(fn)(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator


def apply_limits(app, limiter) -> None:
    """Push the chosen limits onto the currently-known routes.

    Called by the app factory after blueprints are registered so the
    limits bind to real route endpoints, not import-time decorators.
    """
    if limiter is None:
        return

    # (route-key, rate) pairs. The route keys are the Flask
    # endpoint names, which are stable.
    per_route = (
        ("auth.login", "10 per minute"),
        ("auth.register", "5 per minute"),
        ("project_reports.create_report", "10 per minute"),
        ("project_website.refresh_context", "10 per minute"),
    )
    for route_name, spec in per_route:
        view = app.view_functions.get(route_name)
        if view is None:
            continue
        app.view_functions[route_name] = limiter.limit(spec)(view)
