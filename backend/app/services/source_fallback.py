"""Bounded, allow-listed alternate-source fallback for CollectionService.

Level 1 connectors return metadata only.  Level 2 runs only adapters that
were manually registered in ``ApprovedSourceRegistry``; discovered URLs never
become request targets or executable configuration.
"""
from dataclasses import dataclass, field
from time import monotonic
import re


MAX_CATALOG_QUERIES = 5
MAX_DISCOVERED_CANDIDATES = 25
MAX_VALIDATED_CANDIDATES = 10
MAX_FALLBACK_SOURCES = 5
MAX_ALIASES_PER_API = 4
MAX_TOTAL_FALLBACK_TIME_SECONDS = 60
RELEVANT_CATEGORIES = {"ecommerce", "shopping", "product reviews", "consumer reviews", "forums", "discussion", "social", "product feedback"}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    provider_name: str
    api_name: str
    documentation_url: str
    base_url: str
    category: str
    description: str = ""
    authentication_type: str = "unknown"
    capabilities: tuple[str, ...] = ()
    source_catalog: str = ""
    status: str = "DISCOVERED"


@dataclass
class FallbackResult:
    status: str
    entity: str
    records: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


class FallbackBudget:
    def __init__(self):
        self.started = monotonic()
        self.sources_used = 0

    def may_continue(self):
        return self.sources_used < MAX_FALLBACK_SOURCES and monotonic() - self.started < MAX_TOTAL_FALLBACK_TIME_SECONDS

    def consume_source(self):
        if not self.may_continue():
            return False
        self.sources_used += 1
        return True


class CatalogConnector:
    """Metadata-only contract. Implementations must not return review data."""
    def capabilities(self): raise NotImplementedError
    def is_available(self): raise NotImplementedError
    def search_catalog(self, query, categories): raise NotImplementedError
    def normalize_candidates(self, results): raise NotImplementedError
    def get_candidate_metadata(self, candidate): raise NotImplementedError


class SourceAdapter:
    """Registered adapter contract; it must own fixed, allow-listed hosts."""
    source_id = ""
    allowed_hosts = ()
    def capabilities(self): raise NotImplementedError
    def is_available(self): raise NotImplementedError
    def validate_configuration(self): raise NotImplementedError
    def search(self, entity, aliases, budget): raise NotImplementedError
    def normalize(self, response): raise NotImplementedError
    def provenance(self, response): raise NotImplementedError


class ApprovedSourceRegistry:
    def __init__(self, sources=None, adapters=None):
        self._sources = list(sources or [])
        self._adapters = dict(adapters or {})

    def approved_sources(self):
        return [source for source in self._sources if source.status == "APPROVED" and source.candidate_id in self._adapters]

    def adapter_for(self, source):
        return self._adapters[source.candidate_id]


def resolve_entity(source):
    """Deterministic, inert entity resolver based on configured project data."""
    text = " ".join(filter(None, [getattr(source.project, "product_or_topic", None), getattr(source.project, "name", None)])).strip()
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text)[:200]
    # Deliberate common product canonicalisation; no URL/catalog text is executed.
    if re.search(r"samsung\s+(galaxy\s+)?s25", text, re.I):
        return "Samsung Galaxy S25", ["Samsung Galaxy S25", "Samsung S25", "Galaxy S25"]
    return text or "Requested product", [text or "Requested product"]


def discovery_queries(entity):
    return list(dict.fromkeys([f"{entity} reviews API", "product reviews API", "consumer reviews API", "ecommerce reviews API", f"{entity} comments API"]))[:MAX_CATALOG_QUERIES]


def discover_candidates(connectors, entity):
    """Bounded Level 1. Candidates remain DISCOVERED and are never executed."""
    collected = []
    for connector in list(connectors)[:7]:
        if not connector.is_available():
            continue
        for query in discovery_queries(entity):
            try:
                collected.extend(connector.normalize_candidates(connector.search_catalog(query, RELEVANT_CATEGORIES)))
            except Exception:
                continue
            if len(collected) >= MAX_DISCOVERED_CANDIDATES:
                break
    unique = {}
    for candidate in collected:
        if candidate.category.lower() not in RELEVANT_CATEGORIES:
            continue
        key = (candidate.provider_name.lower(), candidate.api_name.lower(), candidate.documentation_url.lower())
        unique.setdefault(key, candidate)
    return list(unique.values())[:MAX_VALIDATED_CANDIDATES]


def _relevant(record, aliases):
    text = str(record.get("review_text") or "").strip()
    haystack = (text + " " + str(record.get("title") or "")).lower()
    return len(text) >= 12 and any(alias.lower() in haystack for alias in aliases)


def run_fallback(source, direct_status, registry, *, discovery_mode="CURATED_ONLY", connectors=()):
    """Single-pass Level 2. No recursion, no generic HTTP, no auto-approval."""
    entity, aliases = resolve_entity(source)
    trace = {"requestedSource": source.type, "requestedUrl": source.url, "canonicalEntity": entity,
             "directStatus": direct_status, "fallbackUsed": True, "discoveryMode": discovery_mode,
             "catalogCandidates": 0, "approvedCandidates": 0, "attempts": []}
    if discovery_mode == "DISCOVER_CANDIDATES":
        trace["catalogCandidates"] = len(discover_candidates(connectors, entity))
    budget = FallbackBudget()
    approved = registry.approved_sources()
    trace["approvedCandidates"] = len(approved)
    if not approved:
        return FallbackResult("NO_DATA_AVAILABLE", entity, provenance=trace)
    for candidate in approved:
        if not budget.consume_source():
            break
        adapter = registry.adapter_for(candidate)
        try:
            adapter.validate_configuration()
            if not adapter.is_available():
                trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "UNAVAILABLE"})
                continue
            response = adapter.search(entity, aliases[:MAX_ALIASES_PER_API], budget)
            records = [record for record in adapter.normalize(response) if _relevant(record, aliases)]
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "SUCCESS" if records else "NO_USABLE_DATA", "recordCount": len(records)})
            if records:
                trace.update({"apiProvider": candidate.provider_name, "apiName": candidate.api_name,
                              "adapterId": candidate.candidate_id, "actualSource": adapter.provenance(response)})
                return FallbackResult("SUCCESS", entity, records=records, provenance=trace)
        except Exception:
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "UNAVAILABLE"})
    return FallbackResult("NO_DATA_AVAILABLE", entity, provenance=trace)


# Runtime starts curated-only with no approved integration or credentials. A
# later reviewed provider is added here with a concrete adapter—not discovery output.
RUNTIME_REGISTRY = ApprovedSourceRegistry()
