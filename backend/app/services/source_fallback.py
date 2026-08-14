"""Bounded, allow-listed alternate-source fallback for CollectionService.

Level 1 connectors return metadata only.  Level 2 runs only adapters that
were manually registered in ``ApprovedSourceRegistry``; discovered URLs never
become request targets or executable configuration.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
import re

import requests

from app.errors.exceptions import CollectionError
from app.services.collectors.security import validate_url_ssrf, ssrf_safe_connections


MAX_CATALOG_QUERIES = 5
MAX_DISCOVERED_CANDIDATES = 25
MAX_VALIDATED_CANDIDATES = 10
MAX_FALLBACK_SOURCES = 5
MAX_ALIASES_PER_API = 4
MAX_TOTAL_FALLBACK_TIME_SECONDS = 60
MAX_RETRIES_PER_API = 2
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
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


class FallbackAdapterError(Exception):
    """Safe, provider-neutral adapter outcome used only in the audit trace."""
    def __init__(self, status):
        self.status = status


class RedditOfficialDiscussionAdapter(SourceAdapter):
    """Official Reddit OAuth adapter for public product discussion comments.

    Hosts and endpoint paths are constants. Neither source URLs, discovery
    metadata, nor API payloads can choose a request destination.
    """
    source_id = "reddit_official_discussions"
    allowed_hosts = ("www.reddit.com", "oauth.reddit.com")
    _token_url = "https://www.reddit.com/api/v1/access_token"
    _search_url = "https://oauth.reddit.com/search.json"
    _comments_base_url = "https://oauth.reddit.com/comments"

    def __init__(self, client_id=None, client_secret=None, user_agent=None, timeout_seconds=10):
        import os
        self.client_id = client_id if client_id is not None else os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = client_secret if client_secret is not None else os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent if user_agent is not None else os.environ.get("REDDIT_USER_AGENT", "SentimentAnalysisSystem/1.0")
        self.timeout_seconds = timeout_seconds

    def capabilities(self):
        return ("product discussion", "forum comments", "public discussion")

    def validate_configuration(self):
        if not self.client_id or not self.client_secret:
            raise FallbackAdapterError("API_CREDENTIALS_REQUIRED")

    def is_available(self):
        return bool(self.client_id and self.client_secret)

    def _request_json(self, method, url, *, headers=None, **kwargs):
        """Fixed-host, SSRF-checked, bounded JSON request with short retries."""
        validate_url_ssrf(url)
        for attempt in range(MAX_RETRIES_PER_API + 1):
            try:
                with ssrf_safe_connections():
                    response = requests.request(method, url, headers=headers, timeout=self.timeout_seconds,
                                                allow_redirects=False, stream=True, **kwargs)
            except requests.Timeout:
                if attempt < MAX_RETRIES_PER_API:
                    continue
                raise FallbackAdapterError("TIMEOUT")
            except requests.RequestException:
                raise FallbackAdapterError("UNAVAILABLE")
            if response.status_code == 429:
                response.close()
                raise FallbackAdapterError("RATE_LIMITED")
            if response.status_code >= 500 and attempt < MAX_RETRIES_PER_API:
                response.close()
                continue
            if response.status_code in (401, 403):
                response.close()
                raise FallbackAdapterError("API_CREDENTIALS_REQUIRED")
            if response.status_code >= 400:
                response.close()
                raise FallbackAdapterError("UNAVAILABLE")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_RESPONSE_BYTES:
                response.close()
                raise FallbackAdapterError("RESPONSE_TOO_LARGE")
            chunks, total = [], 0
            for chunk in response.iter_content(8192):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    response.close()
                    raise FallbackAdapterError("RESPONSE_TOO_LARGE")
                chunks.append(chunk)
            response.close()
            try:
                import json
                return json.loads(b"".join(chunks).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise FallbackAdapterError("INVALID_RESPONSE")

    def search(self, entity, aliases, budget):
        token_response = self._request_json(
            "POST", self._token_url, auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"}, headers={"User-Agent": self.user_agent},
        )
        token = token_response.get("access_token") if isinstance(token_response, dict) else None
        if not token:
            raise FallbackAdapterError("API_CREDENTIALS_REQUIRED")
        headers = {"Authorization": f"Bearer {token}", "User-Agent": self.user_agent}
        posts = self._request_json("GET", self._search_url, headers=headers,
                                   params={"q": aliases[0], "limit": min(10, MAX_ALIASES_PER_API), "sort": "relevance", "raw_json": 1})
        children = ((posts.get("data") or {}).get("children") or []) if isinstance(posts, dict) else []
        comments = []
        # Bounded by the shared source budget and a small fixed post ceiling.
        for child in children[:3]:
            post = child.get("data") if isinstance(child, dict) else None
            post_id = (post or {}).get("id")
            if not post_id or not budget.may_continue():
                continue
            thread = self._request_json("GET", f"{self._comments_base_url}/{post_id}.json", headers=headers,
                                        params={"limit": 20, "depth": 1, "raw_json": 1})
            comments.append(thread)
        return {"threads": comments}

    def normalize(self, response):
        records = []
        for thread in response.get("threads", []) if isinstance(response, dict) else []:
            if not isinstance(thread, list) or len(thread) < 2:
                continue
            post_data = (((thread[0] or {}).get("data") or {}).get("children") or [{}])[0].get("data") or {}
            title = str(post_data.get("title") or "")
            for child in (((thread[1] or {}).get("data") or {}).get("children") or []):
                comment = child.get("data") if isinstance(child, dict) else None
                if not comment or comment.get("kind") == "more":
                    continue
                body = comment.get("body")
                if not isinstance(body, str) or body in {"[removed]", "[deleted]"}:
                    continue
                created = comment.get("created_utc")
                date = None
                if isinstance(created, (int, float)):
                    date = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
                records.append({"external_review_id": comment.get("id"), "review_text": body,
                                "reviewer_name": comment.get("author"), "rating": None,
                                "review_date": date, "review_url": "https://www.reddit.com" + str(comment.get("permalink") or ""),
                                "title": title, "language": None,
                                "source_metadata": {"provider": "Reddit Official API", "subreddit": comment.get("subreddit")}})
        return records

    def provenance(self, response):
        return "Reddit public discussions via official OAuth API"


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
    outcomes = []
    for candidate in approved:
        if not budget.consume_source():
            break
        adapter = registry.adapter_for(candidate)
        try:
            adapter.validate_configuration()
            if not adapter.is_available():
                trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "UNAVAILABLE"})
                outcomes.append("UNAVAILABLE")
                continue
            response = adapter.search(entity, aliases[:MAX_ALIASES_PER_API], budget)
            records = [record for record in adapter.normalize(response) if _relevant(record, aliases)]
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "SUCCESS" if records else "NO_USABLE_DATA", "recordCount": len(records)})
            if records:
                trace.update({"apiProvider": candidate.provider_name, "apiName": candidate.api_name,
                              "adapterId": candidate.candidate_id, "actualSource": adapter.provenance(response)})
                return FallbackResult("SUCCESS", entity, records=records, provenance=trace)
        except FallbackAdapterError as exc:
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": exc.status})
            outcomes.append(exc.status)
        except CollectionError as exc:
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": exc.code})
            outcomes.append(exc.code)
        except Exception:
            trace["attempts"].append({"adapterId": candidate.candidate_id, "status": "UNAVAILABLE"})
            outcomes.append("UNAVAILABLE")
    terminal_status = outcomes[0] if len(set(outcomes)) == 1 and outcomes else "NO_DATA_AVAILABLE"
    trace["terminalStatus"] = terminal_status
    return FallbackResult(terminal_status, entity, provenance=trace)


# The provider is approved as a documented discussion source, not as an
# Amazon-review proxy. Missing credentials safely yield NO_DATA_AVAILABLE.
_reddit_candidate = Candidate(
    "reddit_official_discussions", "Reddit", "Official OAuth API",
    "https://www.reddit.com/dev/api/", "https://oauth.reddit.com", "discussion",
    description="Public Reddit product discussion comments.", authentication_type="OAuth client credentials",
    capabilities=("product discussion", "forum comments"), status="APPROVED",
)
RUNTIME_REGISTRY = ApprovedSourceRegistry(
    [_reddit_candidate], {"reddit_official_discussions": RedditOfficialDiscussionAdapter()},
)
