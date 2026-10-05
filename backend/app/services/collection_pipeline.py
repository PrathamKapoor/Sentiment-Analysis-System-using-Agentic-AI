"""Deterministic three-level collection sequencing over trusted adapters."""
import re
from dataclasses import dataclass, field
from time import monotonic

from flask import current_app

from app.services.entity_resolver import resolve_project_entity
from app.services.product_discovery import deterministic_discovery, discover_product_terms
from app.services.product_discovery import match_product_identity
from app.services.scraping_providers import configured_scraping_providers
from app.services.source_fallback import RUNTIME_REGISTRY, run_fallback


def _usable(records):
    return [record for record in (records or [])
            if isinstance(record, dict) and isinstance(record.get("review_text"), str)
            and record["review_text"].strip()]


def _append_collection_metadata(record, level, method, provider=None):
    metadata = record.setdefault("source_metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        record["source_metadata"] = metadata
    metadata["collection"] = {
        "level": level,
        "method": method,
        **({"provider": provider} if provider else {}),
    }


def _identity_verified_records(records, entity):
    verified = []
    for record in _usable(records):
        metadata = record.get("source_metadata") if isinstance(record.get("source_metadata"), dict) else {}
        title = metadata.get("productTitle") or metadata.get("product_title") or metadata.get("title") or record.get("title") or ""
        candidate = {
            **record,
            "title": title,
            "product_url": metadata.get("productUrl") or record.get("product_url"),
            "sku": metadata.get("sku") or record.get("sku"),
        }
        match = match_product_identity(entity, candidate)
        if match["matched"]:
            if not isinstance(record.get("source_metadata"), dict):
                record["source_metadata"] = {}
            record["source_metadata"]["identityMatch"] = match
            verified.append(record)
    return verified


@dataclass
class CollectionPipelineResult:
    records: list = field(default_factory=list)
    fallback: object = None
    attempts: list = field(default_factory=list)
    final_level: int = 1
    identity_discovery: dict = field(default_factory=dict)


def collect_with_fallbacks(source, direct_records, direct_status, *, settings=None,
                           scraping_providers=None, fallback_registry=None,
                           discovery=None, identity_hint=None):
    """Try direct, configured scraper, then approved retrieval with LLM terms.

    No model output is treated as evidence or as a URL. Level 3 retrieval uses
    only the existing manually approved adapter registry.
    """
    settings = settings or current_app.config
    original_records = list(direct_records or [])
    records = _usable(original_records)
    attempts = [{"level": 1, "method": "direct", "status": "success" if records else direct_status,
                 "recordCount": len(records)}]
    for record in original_records:
        if _usable([record]):
            _append_collection_metadata(record, 1, "direct")
    result = CollectionPipelineResult(records=original_records, attempts=attempts, final_level=1)
    max_level = int(settings.get("COLLECTION_MAX_LEVEL", 3))
    if records or max_level < 2:
        return result
    if not settings.get("COLLECTION_REQUIRE_IDENTITY_MATCH", True):
        result.attempts.append({"level": 2, "method": "third_party_scraping_api", "status": "skipped",
                                "reason": "identity_match_requirement_is_fail_closed"})
        return result

    entity = resolve_project_entity(source.project, source.url)
    identity_terms = []
    if isinstance(identity_hint, dict):
        product_title = identity_hint.get("productTitle")
        asin = identity_hint.get("asin")
        if isinstance(product_title, str) and product_title.strip():
            product_title = " ".join(product_title.split())[:500]
            entity["canonicalName"] = product_title
            entity["product"] = product_title
            entity["aliases"] = list(dict.fromkeys([product_title, *(entity.get("aliases") or [])]))
            identity_terms.append(product_title)
        if isinstance(asin, str) and asin.strip():
            asin = asin.strip().upper()[:20]
            if re.fullmatch(r"[A-Z0-9]{10}", asin):
                entity["identifiers"] = {**(entity.get("identifiers") or {}), "asin": asin}
                entity["sku"] = entity.get("sku") or asin
                identity_terms.append(asin)
    search_terms = list(entity.get("aliases") or [entity.get("canonicalName", "")])
    search_terms = list(dict.fromkeys([*identity_terms, *search_terms]))
    providers = scraping_providers if scraping_providers is not None else configured_scraping_providers()
    if settings.get("COLLECTION_SCRAPING_ENABLED", True):
        for provider in providers:
            if not provider.supports(source):
                continue
            provider_started = monotonic()
            try:
                outcome = provider.collect(source, entity, search_terms)
            except Exception:
                from app.services.scraping_providers import ScrapingResult
                outcome = ScrapingResult("unavailable", provider=getattr(provider, "name", "configured"),
                                         reason="provider_internal_error",
                                         duration_ms=int((monotonic() - provider_started) * 1000))
            records = _identity_verified_records(outcome.records, entity)
            attempts.append({"level": 2, "method": "third_party_scraping_api", "provider": outcome.provider,
                             "status": outcome.status, "reason": outcome.reason or None,
                             "recordCount": len(records), "durationMs": outcome.duration_ms})
            if records:
                for record in records:
                    _append_collection_metadata(record, 2, "third_party_scraping_api", outcome.provider)
                result.records, result.final_level = original_records + records, 2
                return result
    if max_level < 3:
        return result

    # The adapter registry is fixed and manually approved. Discovery terms
    # can refine its bounded query only; they never choose a network target.
    registry = fallback_registry if fallback_registry is not None else RUNTIME_REGISTRY
    if settings.get("PRODUCT_DISCOVERY_LLM_ENABLED", True) and settings.get("COLLECTION_LLM_FALLBACK_ENABLED", True):
        try:
            if discovery:
                identity_discovery = discovery(entity.get("canonicalName", ""))
            else:
                identity_discovery = discover_product_terms(
                    entity.get("canonicalName", ""),
                    sku=entity.get("sku"), canonical_url=entity.get("canonicalUrl"),
                    identifiers=entity.get("identifiers"),
                )
        except Exception:
            identity_discovery = deterministic_discovery(entity.get("canonicalName", ""))
    else:
        identity_discovery = deterministic_discovery(entity.get("canonicalName", ""))
    result.identity_discovery = identity_discovery
    query_terms = list(identity_terms)
    query_terms.extend(identity_discovery.get("search_keywords") or [])
    query_terms.extend(search_terms)
    query_terms = list(dict.fromkeys(term for term in query_terms if isinstance(term, str) and term.strip()))[:20]
    fallback_started = monotonic()
    fallback = run_fallback(
        source, direct_status, registry,
        discovery_mode=settings.get("SOURCE_FALLBACK_DISCOVERY_MODE", "CURATED_ONLY"),
        search_terms=query_terms,
    )
    result.fallback = fallback
    records = _identity_verified_records(fallback.records, entity)
    is_llm_assisted = identity_discovery.get("provider_role") in {"main", "fallback"}
    attempts.append({
        "level": 3, "method": "llm_assisted_approved_retrieval" if is_llm_assisted else "approved_source_retrieval",
        "provider": fallback.provenance.get("apiProvider"),
        "llmProviderRole": identity_discovery.get("provider_role"),
        "llmModel": identity_discovery.get("model_name"),
        "status": "success" if records else fallback.status.lower(),
        "recordCount": len(records),
        "identityMatchCount": sum(1 for item in records if (item.get("source_metadata") or {}).get("identityMatch", {}).get("status") == "verified"),
        "durationMs": int((monotonic() - fallback_started) * 1000),
    })
    if records:
        fallback.provenance["collectionLevel"] = 3
        fallback.provenance["collectionMethod"] = attempts[-1]["method"]
        fallback.provenance["identityDiscovery"] = {
            "providerRole": identity_discovery.get("provider_role"),
            "provider": identity_discovery.get("provider"),
            "model": identity_discovery.get("model_name"),
            "status": identity_discovery.get("status"),
        }
        for record in records:
            _append_collection_metadata(record, 3, attempts[-1]["method"], fallback.provenance.get("apiProvider"))
        result.records, result.final_level = original_records + records, 3
    return result
