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
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from flask import current_app

from app.extensions import db
from app.errors.exceptions import CollectionError
from app.models import DataSource, Review, AuditLog
from app.services.audit_service import log_action
from app.services.text_cleaning import clean_text, normalize_for_dedup
from app.services.dataset_service import _parse_rating, _parse_date
from app.services.collectors.base import CollectionLimits
from app.services.collectors.base import CollectorResult
from app.services.collectors.registry import get_collector, describe_all_source_types
from app.services.collectors.robots import is_collection_allowed_by_robots
from app.services.collectors.security import validate_url_shape
from app.services.entity_resolver import resolve_project_entity
from app.services.project_keyword_matching import evaluate_record_keywords
from app.services.collection_pipeline import collect_with_fallbacks
from app.services.source_fallback import RUNTIME_REGISTRY

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


def _review_provenance(raw):
    """Keep small, safe source references; external metadata is untrusted."""
    record_id = raw.get("external_review_id")
    if record_id is not None:
        record_id = str(record_id).strip()[:255] or None

    source_url = None
    candidate = raw.get("review_url")
    if isinstance(candidate, str) and len(candidate) <= 8192:
        try:
            parsed = urlsplit(candidate)
            if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
                host = parsed.hostname.encode("idna").decode("ascii")
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                if parsed.port:
                    host = f"{host}:{parsed.port}"
                source_url = urlunsplit((parsed.scheme.lower(), host, parsed.path[:2048], "", ""))[:2048]
        except (UnicodeError, ValueError):
            source_url = None

    metadata = raw.get("source_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 8192:
            metadata = {}
    except (TypeError, ValueError):
        metadata = {}
    return record_id, source_url, metadata


@contextmanager
def _serialized_collection():
    """Process-wide serialization for outbound collection calls
    (test_connection, preview_source, collect_source).

    Why this is kept: collection is intentionally sequential at process
    level (AGENTS.md §23) — one fetch chain at a time honors the delay,
    max-pages, and rate-limit budgets shared across sources, and gives
    stable 503 COLLECTION_BUSY behaviour under load. Historically this
    lock also prevented a race in ssrf_safe_connections(), which swapped
    a module-level urllib3 function for the duration of one HTTP call;
    that monkeypatch race is now gone (security.py installs the guard
    once with a thread-local armed flag), so concurrent guarded fetches
    can no longer un-patch each other. The serialization itself is a
    deliberate product behaviour, not just a race guard.

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

    if source.type == "github_issues":
        # This collector targets GitHub's fixed official REST API host, not
        # arbitrary web pages. Its repository URL is only an identifier;
        # the API destination and each connection are SSRF-validated by the
        # collector. robots.txt governs HTML crawlers, not this API client.
        return "allowed"

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

    direct_error_details = {}
    try:
        if current_app.config.get("COLLECTION_DIRECT_ENABLED", True):
            result = collector.collect(source, options)
        else:
            result = CollectorResult(
                fetch_status="skipped", result_code="COLLECTION_DIRECT_DISABLED",
                result_message="Direct collection is disabled by server configuration.",
                adapter=collector.collector_type,
            )
    except CollectionError as exc:
        if exc.code in {"COLLECTION_TIMEOUT", "COLLECTION_HTTP_ERROR", "COLLECTION_PARSE_ERROR"}:
            direct_error_details = dict(exc.details or {})
            result = CollectorResult(
                fetch_status="failed", result_code=exc.code,
                result_message=exc.message, warnings=[exc.message], adapter=collector.collector_type,
                product_identity=(exc.details or {}).get("productIdentity"),
                product_title=(exc.details or {}).get("productTitle"),
            )
        elif (
            exc.code == "COLLECTION_BLOCKED"
            and collector.collector_type == "ecommerce"
            and (exc.details or {}).get("adapter") == "amazon_india"
            and (exc.details or {}).get("reviewPageStatus") == "SIGN_IN"
        ):
            # Amazon's sign-in response stops Amazon collection. Only the
            # independent approved fallback pipeline may be tried next.
            result = CollectorResult(
                fetch_status="blocked", result_code=exc.code,
                result_message=exc.message, warnings=[exc.message],
                adapter=collector.collector_type, review_page_status="SIGN_IN",
                product_identity=(exc.details or {}).get("productIdentity"),
                product_title=(exc.details or {}).get("productTitle"),
            )
        else:
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

    pipeline = collect_with_fallbacks(
        source,
        result.records,
        result.result_code or ("NO_RECORDS" if not result.records else "SUCCESS"),
        fallback_registry=RUNTIME_REGISTRY,
        identity_hint=(
            {"productTitle": result.product_title, "asin": result.product_identity}
            if collector.collector_type == "ecommerce"
            and (urlsplit(source.url).hostname or "").casefold().removeprefix("www.") == "amazon.in"
            else None
        ),
    )
    direct_failure_code = result.result_code if result.fetch_status == "failed" else None
    fallback = pipeline.fallback
    result.records = pipeline.records
    if pipeline.final_level > 1:
        result.fetch_status = "fallback"
    if not result.records and fallback:
        if fallback.status == "API_CREDENTIALS_REQUIRED":
            result.result_code = "FALLBACK_CREDENTIALS_REQUIRED"
            result.result_message = "An approved fallback provider is available but is not configured. Server-side API credentials are required."
        elif fallback.status == "RATE_LIMITED":
            result.result_code = "FALLBACK_RATE_LIMITED"
            result.result_message = "The approved fallback provider is temporarily rate limited. Try again later."
        elif fallback.status != "NO_DATA_AVAILABLE":
            result.result_code = "FALLBACK_UNAVAILABLE"
            result.result_message = "The approved fallback provider is currently unavailable. You can upload a dataset instead."
    if not pipeline.records and direct_failure_code in {
        "COLLECTION_TIMEOUT", "COLLECTION_HTTP_ERROR", "COLLECTION_PARSE_ERROR",
    }:
        log_action(organisation_id, actor_user_id, "collection.failed", "data_source", source.id, {
            "errorCode": direct_failure_code,
            "safeErrorMessage": result.result_message or "Direct collection failed and no configured fallback returned usable evidence.",
            "triggerType": trigger_type,
            "collectionPipeline": pipeline.attempts,
        })
        db.session.commit()
        raise CollectionError(
            result.result_message or "Direct collection failed and no configured fallback returned usable evidence.",
            code=direct_failure_code,
            details={**direct_error_details, "collectionPipeline": pipeline.attempts},
        )

    existing_hashes = {
        normalize_for_dedup(r.text)
        for r in Review.query.filter_by(project_id=source.project_id).filter(Review.deleted_at.is_(None)).all()
    }
    seen_hashes = set(existing_hashes)

    inserted = 0
    duplicates = 0
    invalid = 0
    keyword_filtered = 0
    entity = resolve_project_entity(source.project, source.url)
    record_source = (fallback.provenance.get("apiProvider") if fallback and fallback.status == "SUCCESS" else None) or source.type

    try:
        for raw in result.records:
            text = clean_text(raw.get("review_text"))
            if not text:
                invalid += 1
                continue
            keyword_match = evaluate_record_keywords(text, source.keywords, entity)
            if not keyword_match["included"]:
                keyword_filtered += 1
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

            source_record_id, source_url, source_metadata = _review_provenance(raw)

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
                keyword_matches=keyword_match,
                source_record_id=source_record_id,
                source_url=source_url,
                source_metadata=source_metadata,
                source_collected_at=datetime.now(timezone.utc),
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
    if records_found == 0 or (inserted == 0 and keyword_filtered == records_found):
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
        result_message = (
            f"No reviews were saved: {invalid} candidates failed validation and "
            f"{keyword_filtered} were excluded by configured keyword rules."
        )
    elif inserted == 0 and keyword_filtered == records_found and records_found:
        result_code = "COLLECTION_NO_KEYWORD_MATCHES"
        result_message = f"{records_found} candidates were found, but none matched the configured inclusion and exclusion terms."
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
        "recordsFilteredByKeywords": keyword_filtered,
        "recordsAfterKeywordFilter": records_found - keyword_filtered,
        "keywordFilteringStatus": "APPLIED",
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
        # Always 0 by design: duplicates are INSERTED and FLAGGED
        # (is_duplicate=True, counted in recordsDuplicate), never dropped —
        # Phase 2 precedent, pinned by test_duplicate_detection_across_collection_runs.
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
        "collectionPipeline": pipeline.attempts,
        "collectionLevel": pipeline.final_level,
        "identityDiscovery": ({
            "provider": pipeline.identity_discovery.get("provider"),
            "providerRole": pipeline.identity_discovery.get("provider_role"),
            "model": pipeline.identity_discovery.get("model_name"),
            "status": pipeline.identity_discovery.get("status"),
        } if pipeline.identity_discovery else None),
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
