"""Observability helpers — request correlation IDs, structured logging,
step timing.

This module is deliberately tiny. The goals are:

  1. A request id (``X-Request-ID`` header, or auto-generated) is
     available on ``flask.g`` for the duration of a request, and is
     attached to every structured log line.
  2. A ``step_timer`` context manager records ``started_at``,
     ``finished_at``, and ``duration_ms`` on a dict, suitable for
     surfacing in API responses or workflow step results.
  3. ``structured_log`` is a thin convenience over ``app.logger`` that
     includes the request id, actor user id, and any extra fields.

These are best-effort helpers. They never raise, never log secrets, and
never depend on a third-party library.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional

from flask import g, has_request_context, request


REQUEST_ID_HEADER = "X-Request-ID"


def get_or_create_request_id() -> str:
    """Return the current request id, creating one if there isn't one
    already. Safe to call outside of a request context (returns a fresh
    id)."""
    if not has_request_context():
        return _new_id()
    rid = getattr(g, "request_id", None)
    if rid:
        return rid
    incoming = request.headers.get(REQUEST_ID_HEADER) if request else None
    if incoming and len(incoming) <= 128 and all(c.isalnum() or c in "-_." for c in incoming):
        rid = incoming
    else:
        rid = _new_id()
    g.request_id = rid
    return rid


def _new_id() -> str:
    return uuid.uuid4().hex


def current_request_id() -> Optional[str]:
    if not has_request_context():
        return None
    return getattr(g, "request_id", None)


@contextmanager
def step_timer(name: str, *, metadata: Optional[Dict[str, Any]] = None):
    """Context manager that yields a dict and populates ``started_at``,
    ``finished_at`` (ISO strings), ``duration_ms``, ``name``, and
    ``metadata`` on it. The dict is what the caller stores.
    """
    started = time.monotonic()
    started_iso = _now_iso()
    record: Dict[str, Any] = {
        "name": name,
        "startedAt": started_iso,
        "finishedAt": None,
        "durationMs": None,
        "metadata": dict(metadata or {}),
    }
    try:
        yield record
    finally:
        record["finishedAt"] = _now_iso()
        record["durationMs"] = int((time.monotonic() - started) * 1000)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def structured_log(
    logger_obj: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    actor_user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    organisation_id: Optional[str] = None,
    **fields: Any,
) -> None:
    """Log a single line with the request id, actor, and extra fields.
    Never raises, never logs secrets (the caller is responsible for what
    is in ``fields``)."""
    parts = [f"rid={get_or_create_request_id()}"]
    if actor_user_id:
        parts.append(f"actor={actor_user_id}")
    if project_id:
        parts.append(f"project={project_id}")
    if organisation_id:
        parts.append(f"org={organisation_id}")
    for k, v in fields.items():
        if v is None:
            continue
        # Bound each value to keep log lines compact.
        text = str(v)
        if len(text) > 200:
            text = text[:200] + "...[truncated]"
        parts.append(f"{k}={text}")
    try:
        logger_obj.log(level, "%s | %s", message, " ".join(parts))
    except Exception:
        # Never let logging break the request.
        pass
