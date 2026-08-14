"""Orchestrates the 18-step collection flow (see docs/phase6_schema_changes.md
for the reconciliation this design is based on). Steps 1-5 (auth/org/project/
permission/source-exists) are already handled by the route decorators before
any function here is called — this module starts at "validate source" and
owns everything from policy checks through review insertion.

No collection_jobs table: collection is synchronous within the request
(same pattern as dataset validate/process since Phase 2, and every analysis
run since Phase 3 — see README "Testing Notes" in prior phases for why).
Collection status/history are derived from audit_logs + data_sources.last_
collected_at, never duplicated into a separate table.
"""
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.errors.exceptions import CollectionError
from app.models import DataSource, Review, AuditLog
from app.services.audit_service import log_action
from app.services.text_cleaning import clean_text, normalize_for_dedup
from app.services.dataset_service import _parse_rating, _parse_date
from app.services.collectors.base import CollectionLimits
from app.services.collectors.registry import get_collector, describe_all_source_types
from app.services.collectors.robots import is_collection_allowed_by_robots
from app.services.collectors.security import validate_url_shape
from app.services.source_fallback import RUNTIME_REGISTRY, run_fallback

_COLLECTION_HISTORY_ACTIONS = (
    "collection.started", "collection.completed", "collection.failed",
    "collection.blocked_by_policy", "collection.preview", "data_source.test_connection",
)
_COLLECTION_STATUS_ACTIONS = (
    "collection.started", "collection.completed", "collection.failed", "collection.blocked_by_policy",
)

# Guards every collection operation that performs a real network fetch
# (test-connection/preview/collect) — see _serialized_collection() below.
_collection_lock = threading.Lock()
_LOCK_ACQUIRE_TIMEOUT_SECONDS = 30


@contextmanager
def _serialized_collection():
    """Process-wide serialization for anything that calls
    ssrf_safe_connections() (app/services/collectors/security.py).

    Why this is needed: ssrf_safe_connections() monkeypatches a
    module-level urllib3 function for the duration of one HTTP call. If
    two collection requests ran concurrently within the same process
    (Flask's dev server with threaded=True, or any future threaded WSGI
    worker), one request's __exit__ could un-patch the hook while the
    other request's fetch is still relying on it being active — silently
    disabling SSRF protection for the second request. This lock makes
    that impossible by serializing every such call in-process.

    Bounded wait, not indefinite — a stuck lock can't hang every future
    request forever; a caller that can't acquire it within the timeout
    gets a clear, safe "try again" error instead of hanging or a bare 500.
    This only protects the current single-process synchronous
    architecture — a multi-worker/distributed deployment would need a
    different (per-worker or externally-coordinated) mechanism.
    """
    acquired = _collection_lock.acquire(timeout=_LOCK_ACQUIRE_TIMEOUT_SECONDS)
    if not acquired:
        raise CollectionError(
            "Another collection operation is currently in progress on this server. Please try again shortly.",
            code="COLLECTION_BUSY", status_code=503,
        )
    try:
        yield
    finally:
        _collection_lock.release()


def _limits():
    cfg = current_app.config
    return CollectionLimits(
        timeout_seconds=cfg["SCRAPER_REQUEST_TIMEOUT_SECONDS"],
        request_delay_seconds=cfg["SCRAPER_REQUEST_DELAY_SECONDS"],
        max_pages=cfg["SCRAPER_MAX_PAGES"],
        max_records=cfg["SCRAPER_MAX_RECORDS"],
        max_response_mb=cfg["SCRAPER_MAX_RESPONSE_MB"],
        max_retries=cfg["SCRAPER_MAX_RETRIES"],
        max_redirects=cfg["SCRAPER_MAX_REDIRECTS"],
        user_agent=cfg["SCRAPER_USER_AGENT"],
    )


def _policy_for(source, collector, limits):
    """Computed on every call, never persisted (approved data_sources schema
    has no policy column — see docs/phase6_deferred_issues.md). One of:
    allowed / blocked / api_preferred / manual_upload_only.
    """
    if source.type == "reddit":
        health = collector.health_check(source)
        return "allowed" if health["available"] else "api_preferred"

    try:
        validate_url_shape(source.url)
    except CollectionError:
        return "blocked"

    allowed, _checked = is_collection_allowed_by_robots(source.url, limits)
    return "allowed" if allowed else "blocked"


def get_collector_capabilities():
    """Structured, static capability info for every registered source type
    (name, available, unavailableReason, supportsPreview, supportsPagination,
    requiresCredentials) — the entry point for a caller (Phase 7
    orchestration) to check whether a source type can be attempted at all
    before touching a real source. See app/services/collectors/registry.py.
    """
    return describe_all_source_types()


def _require_collector(source, limits):
    collector = get_collector(source.type, limits)
    if collector is None:
        raise CollectionError(
            f"Automated collection is not supported for source type '{source.type}'. Use dataset upload instead.",
            code="COLLECTION_UNSUPPORTED_SOURCE",
        )
    return collector


def test_connection(source, actor_user_id):
    with _serialized_collection():
        limits = _limits()
        collector = _require_collector(source, limits)
        result = collector.health_check(source)
    log_action(source.project.organisation_id, actor_user_id, "data_source.test_connection", "data_source", source.id, {
        "available": result["available"],
    })
    db.session.commit()
    return result


def preview_source(source, actor_user_id, options=None):
    with _serialized_collection():
        return _preview_source_locked(source, actor_user_id, options)


def _preview_source_locked(source, actor_user_id, options):
    limits = _limits()
    collector = _require_collector(source, limits)
    policy = _policy_for(source, collector, limits)

    organisation_id = source.project.organisation_id
    if policy == "blocked":
        log_action(organisation_id, actor_user_id, "collection.blocked_by_policy", "data_source", source.id, {
            "reason": "robots_disallowed", "context": "preview",
        })
        db.session.commit()
        raise CollectionError(
            "Preview is not available: this source's robots.txt disallows automated access. "
            "Use dataset upload instead.", code="COLLECTION_NOT_PERMITTED",
        )

    collector.validate_source(source)
    preview = collector.preview(source, options)
    preview["sourceId"] = str(source.id)
    preview["policy"] = policy
    preview["collectionAllowed"] = policy == "allowed"

    log_action(organisation_id, actor_user_id, "collection.preview", "data_source", source.id, {
        "recordCountEstimate": preview.get("detectedRecordCountEstimate"),
    })
    db.session.commit()
    return preview


def collect_source(source, actor_user_id, trigger_type="manual", options=None):
    """Implements steps 6-18 of the collection flow. Raises CollectionError
    for hard failures (SSRF/policy/network/parse). A soft outcome — zero
    records found, or some records skipped as invalid/duplicate — is
    reported in the returned summary's `status`, never raised as an error:
    "no new reviews this run" is a legitimate result, not a failure.
    """
    with _serialized_collection():
        return _collect_source_locked(source, actor_user_id, trigger_type, options)


def _collect_source_locked(source, actor_user_id, trigger_type, options):
    options = options or {}
    organisation_id = source.project.organisation_id
    started_at = datetime.now(timezone.utc)

    if not source.enabled:
        log_action(organisation_id, actor_user_id, "collection.blocked_by_policy", "data_source", source.id, {
            "reason": "source_disabled", "triggerType": trigger_type,
        })
        db.session.commit()
        raise CollectionError("This data source is disabled.", code="COLLECTION_SOURCE_DISABLED")

    limits = _limits()
    collector = _require_collector(source, limits)
    policy = _policy_for(source, collector, limits)

    if policy == "blocked":
        log_action(organisation_id, actor_user_id, "collection.blocked_by_policy", "data_source", source.id, {
            "reason": "robots_disallowed", "triggerType": trigger_type,
        })
        db.session.commit()
        raise CollectionError(
            "Collection is not permitted for this source (robots.txt disallows automated access). "
            "Use dataset upload instead.", code="COLLECTION_NOT_PERMITTED",
        )
    if policy == "api_preferred":
        log_action(organisation_id, actor_user_id, "collection.blocked_by_policy", "data_source", source.id, {
            "reason": "api_preferred", "triggerType": trigger_type,
        })
        db.session.commit()
        raise CollectionError(
            "This source type requires official API credentials that are not configured. "
            "Use dataset upload instead.", code="COLLECTION_UNSUPPORTED_SOURCE",
        )

    try:
        collector.validate_source(source)
    except CollectionError as exc:
        log_action(organisation_id, actor_user_id, "collection.failed", "data_source", source.id, {
            "errorCode": exc.code, "safeErrorMessage": exc.message, "triggerType": trigger_type,
        })
        db.session.commit()
        raise

    log_action(organisation_id, actor_user_id, "collection.started", "data_source", source.id, {
        "triggerType": trigger_type,
    })
    db.session.commit()

    try:
        result = collector.collect(source, options)
    except CollectionError as exc:
        exc.details = {
            "sourceId": str(source.id),
            "fetchStatus": "failed",
            **(exc.details or {}),
        }
        log_action(organisation_id, actor_user_id, "collection.failed", "data_source", source.id, {
            "errorCode": exc.code, "safeErrorMessage": exc.message, "triggerType": trigger_type,
            **exc.details,
        })
        db.session.commit()
        raise

    fallback = None
    # Level 0 remains authoritative: fallback is considered only after a
    # permitted direct attempt returned no usable records. It cannot turn a
    # catalog discovery result into a network request.
    if not result.records:
        fallback = run_fallback(
            source, result.result_code or "NO_RECORDS", RUNTIME_REGISTRY,
            discovery_mode=current_app.config.get("SOURCE_FALLBACK_DISCOVERY_MODE", "CURATED_ONLY"),
        )
        if fallback.status == "SUCCESS":
            result.records = fallback.records
            result.fetch_status = "fallback"
        elif fallback.status == "API_CREDENTIALS_REQUIRED":
            result.result_code = "FALLBACK_CREDENTIALS_REQUIRED"
            result.result_message = "An approved fallback provider is available but is not configured. Server-side API credentials are required."
        elif fallback.status == "RATE_LIMITED":
            result.result_code = "FALLBACK_RATE_LIMITED"
            result.result_message = "The approved fallback provider is temporarily rate limited. Try again later."
        elif fallback.status != "NO_DATA_AVAILABLE":
            result.result_code = "FALLBACK_UNAVAILABLE"
            result.result_message = "The approved fallback provider is currently unavailable. You can upload a dataset instead."

    existing_hashes = {
        normalize_for_dedup(r.text)
        for r in Review.query.filter_by(project_id=source.project_id).filter(Review.deleted_at.is_(None)).all()
    }
    seen_hashes = set(existing_hashes)

    inserted = 0
    duplicates = 0
    invalid = 0
    record_source = (fallback.provenance.get("apiProvider") if fallback and fallback.status == "SUCCESS" else None) or source.type

    try:
        for raw in result.records:
            text = clean_text(raw.get("review_text"))
            if not text:
                invalid += 1
                continue
            rating, rating_ok = _parse_rating(raw.get("rating"))
            if not rating_ok:
                invalid += 1
                continue

            review_date = _parse_date(raw.get("review_date"))
            text_hash = normalize_for_dedup(text)
            is_dup = text_hash in seen_hashes
            seen_hashes.add(text_hash)
            if is_dup:
                duplicates += 1

            db.session.add(Review(
                project_id=source.project_id,
                data_source_id=source.id,
                text=text,
                reviewer_ref=raw.get("reviewer_name"),
                # Preserve the requested DataSource relation while making the
                # per-review visible source truthful for fallback records.
                source=record_source,
                rating=rating,
                review_date=review_date,
                is_duplicate=is_dup,
            ))
            inserted += 1

        source.last_collected_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log_action(organisation_id, actor_user_id, "collection.failed", "data_source", source.id, {
            "errorCode": "COLLECTION_PARSE_ERROR",
            "safeErrorMessage": "Collected records could not be saved.",
            "triggerType": trigger_type,
        })
        db.session.commit()
        raise CollectionError("Collected records could not be saved.", code="COLLECTION_PARSE_ERROR")

    completed_at = datetime.now(timezone.utc)
    records_found = len(result.records)
    if records_found == 0:
        status = "no_records"
    elif result.truncated or invalid > 0 or result.fetch_status == "partial":
        status = "partial_success"
    else:
        status = "completed"

    if records_found == 0 and fallback and fallback.status == "NO_DATA_AVAILABLE":
        result_code = "NO_DATA_AVAILABLE"
        result_message = f"No approved alternative source returned usable review data for {fallback.entity!r}. You can upload a dataset instead."
    elif records_found == 0:
        result_code = result.result_code or "COLLECTION_NO_REVIEWS_FOUND"
        result_message = result.result_message or "The page loaded, but no review candidates were detected."
    elif inserted == 0 and invalid:
        result_code = "COLLECTION_NO_VALID_REVIEWS"
        result_message = f"{records_found} candidates were detected, but none contained valid review data."
    elif status == "partial_success":
        result_code = "COLLECTION_PARTIAL"
        result_message = f"{inserted} reviews were saved with warnings."
    else:
        result_code = "COLLECTION_SUCCESS"
        result_message = f"{inserted} reviews were collected."

    summary = {
        "sourceId": str(source.id),
        "status": status,
        "recordsFound": records_found,
        "recordsInserted": inserted,
        "recordsDuplicate": duplicates,
        "recordsInvalid": invalid,
        "startedAt": started_at.isoformat(),
        "completedAt": completed_at.isoformat(),
        "pagesFetched": result.pages_fetched,
        "truncated": result.truncated,
        "warnings": result.warnings,
        "fetchStatus": result.fetch_status,
        "httpStatus": result.http_status,
        "adapter": result.adapter,
        "normalizedUrl": result.normalized_url,
        "candidateItemsFound": result.candidate_items_found,
        "itemsParsed": result.items_parsed,
        "itemsAfterFilter": result.items_after_filter,
        "duplicatesSkipped": 0,
        "itemsSaved": inserted,
        "resultCode": result_code,
        "resultMessage": result_message,
        "productIdentity": result.product_identity,
        "productPageStatus": result.product_page_status,
        "productPageHttpStatus": result.product_page_http_status,
        "productPageFinalUrl": result.product_page_final_url,
        "productPageContentType": result.product_page_content_type,
        "productPageRedirectCount": result.product_page_redirect_count,
        "reviewPageStatus": result.review_page_status,
        "reviewPageHttpStatus": result.review_page_http_status,
        "reviewPageFinalUrl": result.review_page_final_url,
        "reviewPageContentType": result.review_page_content_type,
        "reviewPageRedirectCount": result.review_page_redirect_count,
        "reviewDiscoveryMethod": result.review_discovery_method,
        "parserStatus": result.parser_status,
        "fallback": fallback.provenance if fallback else None,
    }

    log_action(organisation_id, actor_user_id, "collection.completed", "data_source", source.id, {
        k: v for k, v in summary.items() if k != "warnings"
    } | {"triggerType": trigger_type})
    db.session.commit()
    return summary


def collect_enabled_sources_for_project(project_id, actor_user_id):
    sources = DataSource.query.filter_by(project_id=project_id, enabled=True).all()
    results = []
    for source in sources:
        try:
            results.append(collect_source(source, actor_user_id, trigger_type="bulk"))
        except CollectionError as exc:
            results.append({
                "sourceId": str(source.id), "status": "failed",
                "errorCode": exc.code, "safeErrorMessage": exc.message,
            })
    return results


def get_collection_status(source):
    latest = (
        AuditLog.query
        .filter_by(entity_type="data_source", entity_id=str(source.id))
        .filter(AuditLog.action.in_(_COLLECTION_STATUS_ACTIONS))
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    return {
        "sourceId": str(source.id),
        "enabled": source.enabled,
        "lastCollectedAt": source.last_collected_at.isoformat() if source.last_collected_at else None,
        "hasEverCollected": source.last_collected_at is not None,
        "lastAction": latest.action if latest else None,
        "lastActionAt": latest.timestamp.isoformat() if latest else None,
        "lastResult": (latest.event_metadata or {}) if latest else None,
    }


def get_collection_history(source, limit=20):
    entries = (
        AuditLog.query
        .filter_by(entity_type="data_source", entity_id=str(source.id))
        .filter(AuditLog.action.in_(_COLLECTION_HISTORY_ACTIONS))
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [e.to_dict() for e in entries]
