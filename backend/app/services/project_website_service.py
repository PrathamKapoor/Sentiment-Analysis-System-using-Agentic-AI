"""Per-project website URL + cached extraction flow.

This service:

  - Validates and persists a user-supplied ``website_url`` on the project.
  - Optionally performs a bounded single-page extraction, reusing the
    same SSRF protections as the rest of the system.
  - Caches the most recent extraction on the ``ProjectWebsiteContext``
    row, so reports can include a stable snapshot and we never re-fetch
    a page just because the report was regenerated.
  - Lets the user clear the URL (and the cached context) at any time.

The product works fully without a URL. The URL is purely an enhancement.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import current_app

from app.errors.exceptions import CollectionError, ValidationError
from app.extensions import db
from app.models import Project, ProjectWebsiteContext
from app.services.audit_service import log_action
from app.services.website_context_service import (
    ALL_STATUSES,
    STATUS_OK,
    extract_website_context,
    validate_url as validate_website_url,
)

logger = logging.getLogger(__name__)


def _scrub_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None
    url = url.strip()
    if not url:
        return None
    return url


def _resolve_actor_and_org(project: Project) -> Tuple[Any, Any]:
    return project.organisation_id, getattr(project, "_actor_user_id", None)


def get_website_context(project: Project) -> Optional[Dict[str, Any]]:
    row = ProjectWebsiteContext.query.filter_by(project_id=project.id).first()
    if row is None:
        return None
    return row.to_dict()


def set_website_url(
    project: Project,
    actor_user_id: Any,
    website_url: Optional[str],
    *,
    auto_refresh: bool = False,
) -> Dict[str, Any]:
    """Persist a new website URL on the project and (optionally) refresh
    the cached extraction. ``website_url`` of None or "" clears the URL
    and the cached context.

    Returns the updated website context dict (possibly ``None`` if both
    URL and cache were cleared).
    """
    if project.deleted_at is not None:
        raise ValidationError("Cannot update a deleted project.")

    cleaned = _scrub_url(website_url)
    if cleaned is not None:
        # Shape check only — full SSRF happens at extraction time so a
        # user can save a URL and only fetch it on demand.
        try:
            validate_website_url(cleaned)
        except CollectionError as exc:
            raise ValidationError(str(exc.message)[:300])

    project.website_url = cleaned
    db.session.add(project)

    if cleaned is None:
        # Clearing: drop the cached row too.
        existing = ProjectWebsiteContext.query.filter_by(project_id=project.id).first()
        if existing is not None:
            db.session.delete(existing)
        log_action(
            project.organisation_id, actor_user_id,
            "project.website_url_cleared", "project", project.id, {},
        )
        db.session.commit()
        return None

    log_action(
        project.organisation_id, actor_user_id,
        "project.website_url_updated", "project", project.id,
        {"hasUrl": True, "autoRefresh": bool(auto_refresh)},
    )
    db.session.commit()

    if auto_refresh:
        return refresh_website_context(project, actor_user_id)

    # Return whatever cached context exists, or a minimal entry.
    existing = ProjectWebsiteContext.query.filter_by(project_id=project.id).first()
    if existing is not None:
        return existing.to_dict()
    return {
        "projectId": str(project.id),
        "websiteUrl": project.website_url,
        "sourceUrl": None,
        "status": "pending",
        "title": None,
        "metaDescription": None,
        "headings": [],
        "bodyExcerpt": None,
        "contentHash": None,
        "failureReason": None,
        "extractedAt": None,
    }


def refresh_website_context(project: Project, actor_user_id: Any) -> Dict[str, Any]:
    """Run a single bounded extraction and cache the result."""
    if not project.website_url:
        raise ValidationError("This project has no website URL set.")

    # The validate_url call re-raises CollectionError for the API to map.
    validate_website_url(project.website_url)

    extraction = extract_website_context(project.website_url)

    row = ProjectWebsiteContext.query.filter_by(project_id=project.id).first()
    if row is None:
        row = ProjectWebsiteContext(project_id=project.id)
        db.session.add(row)
    row.website_url = project.website_url
    row.source_url = extraction.url
    row.status = extraction.status if extraction.status in ALL_STATUSES else "fetch_failed"
    row.title = extraction.title or None
    row.meta_description = extraction.meta_description or None
    row.headings = list(extraction.headings or [])
    row.body_excerpt = extraction.body_excerpt or None
    row.content_hash = extraction.content_hash or None
    row.failure_reason = (extraction.failure_reason or "")[:500] or None
    row.extracted_at = datetime.now(timezone.utc)

    log_action(
        project.organisation_id, actor_user_id,
        "project.website_context_refreshed", "project", project.id,
        {
            "status": row.status,
            "elapsedMs": extraction.elapsed_ms,
            "contentHash": row.content_hash,
        },
    )
    db.session.commit()
    return row.to_dict()
