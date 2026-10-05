"""Deterministic canonical entity resolution for project collection."""
import re
from urllib.parse import unquote, urlparse

from app.models import ProjectEntity


def _clean_terms(values):
    result = []
    seen = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        term = re.sub(r"\s+", " ", value).strip()[:200]
        key = term.casefold()
        if term and key not in seen:
            seen.add(key)
            result.append(term)
    return result


def _slug_product_name(url):
    if not url:
        return None
    try:
        segments = [part for part in urlparse(url).path.split("/") if part]
    except (TypeError, ValueError):
        return None
    if not segments:
        return None
    candidate = unquote(segments[0])
    candidate = re.sub(r"[-_]+", " ", candidate)
    candidate = re.sub(r"\b(?:p|dp|product|item)\b", " ", candidate, flags=re.I)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    return candidate[:200] or None


def resolve_project_entity(project, source_url=None):
    """Return a bounded, deterministic entity description for adapters.

    A stored canonical entity takes priority. Legacy projects fall back to
    ``product_or_topic`` and a product-like path segment from the configured
    source URL. The resolver never performs network access or trusts page data.
    """
    entity = ProjectEntity.query.filter_by(project_id=project.id).first()
    if entity:
        canonical = entity.canonical_name
        aliases = _clean_terms([canonical, *(entity.aliases or []), entity.sku])
        return {
            "canonicalName": canonical or (project.product_or_topic or project.name),
            "brand": entity.brand,
            "product": entity.product,
            "model": entity.model,
            "sku": entity.sku,
            "canonicalUrl": entity.canonical_url,
            "aliases": aliases,
            "identifiers": dict(entity.identifiers or {}),
            "includeKeywords": list(entity.include_keywords or []),
            "excludeKeywords": list(entity.exclude_keywords or []),
            "securityKeywords": list(entity.security_keywords or []),
            "competitorKeywords": list(entity.competitor_keywords or []),
            "customKeywords": list(entity.custom_keywords or []),
        }

    fallback_name = (project.product_or_topic or "").strip() or _slug_product_name(source_url) or project.name
    return {
        "canonicalName": fallback_name,
        "brand": None,
        "product": fallback_name,
        "model": None,
        "sku": None,
        "canonicalUrl": source_url,
        "aliases": _clean_terms([fallback_name]),
        "identifiers": {},
        "includeKeywords": [],
        "excludeKeywords": [],
        "securityKeywords": [],
        "competitorKeywords": [],
        "customKeywords": [],
    }
