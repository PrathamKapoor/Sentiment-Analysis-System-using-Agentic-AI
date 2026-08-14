from types import SimpleNamespace
from contextlib import nullcontext
import json

import pytest
import requests

from app.services.source_fallback import (
    ApprovedSourceRegistry, Candidate, SourceAdapter, discover_candidates,
    discovery_queries, run_fallback, RedditOfficialDiscussionAdapter, FallbackAdapterError,
)


def _source():
    return SimpleNamespace(
        type="amazon", url="https://www.amazon.in/dp/example",
        project=SimpleNamespace(product_or_topic="Samsung s25", name="Samsung phones"),
    )


class _Adapter(SourceAdapter):
    def validate_configuration(self): pass
    def is_available(self): return True
    def search(self, entity, aliases, budget):
        assert entity == "Samsung Galaxy S25"
        assert len(aliases) <= 4
        return {"items": True}
    def normalize(self, response):
        return [
            {"review_text": "Samsung Galaxy S25 has an excellent display and battery life.", "rating": 5},
            {"review_text": "Galaxy S24 is fine but unrelated to this request.", "rating": 4},
        ]
    def provenance(self, response): return "Example permitted review API"


def test_approved_adapter_returns_relevant_reviews_with_true_provenance():
    candidate = Candidate("example", "Example", "Reviews", "https://docs.example.test", "https://api.example.test", "product reviews", status="APPROVED")
    result = run_fallback(_source(), "NO_SUPPORTED_ELEMENTS", ApprovedSourceRegistry([candidate], {"example": _Adapter()}))
    assert result.status == "SUCCESS"
    assert len(result.records) == 1
    assert result.provenance["requestedSource"] == "amazon"
    assert result.provenance["actualSource"] == "Example permitted review API"


def test_unapproved_discovery_is_never_executed():
    result = run_fallback(_source(), "NO_RECORDS", ApprovedSourceRegistry())
    assert result.status == "NO_DATA_AVAILABLE"
    assert result.provenance["approvedCandidates"] == 0


class _Catalog:
    def is_available(self): return True
    def search_catalog(self, query, categories):
        return [
            Candidate("a", "Provider", "Reviews", "https://docs.example.test", "https://api.example.test", "product reviews"),
            Candidate("weather", "Weather", "Weather", "https://weather.example.test", "https://weather.example.test", "weather"),
        ]
    def normalize_candidates(self, results): return results


def test_discovery_is_bounded_deduplicated_and_metadata_only():
    found = discover_candidates([_Catalog()], "Samsung Galaxy S25")
    assert len(discovery_queries("Samsung Galaxy S25")) == 5
    assert len(found) == 1
    assert found[0].status == "DISCOVERED"


class _Response:
    def __init__(self, body, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    def iter_content(self, _size): yield self.body
    def close(self): pass


def _safe_adapter(monkeypatch):
    monkeypatch.setattr("app.services.source_fallback.validate_url_ssrf", lambda _url: None)
    monkeypatch.setattr("app.services.source_fallback.ssrf_safe_connections", nullcontext)
    return RedditOfficialDiscussionAdapter("id", "secret", timeout_seconds=1)


def test_reddit_official_adapter_normalizes_comment_and_provenance(monkeypatch):
    adapter = _safe_adapter(monkeypatch)
    responses = iter([
        _Response({"access_token": "token"}),
        _Response({"data": {"children": [{"data": {"id": "post1"}}]}}),
        _Response([{"data": {"children": [{"data": {"title": "Samsung Galaxy S25 review"}}]}},
                   {"data": {"children": [{"data": {"id": "c1", "body": "Samsung Galaxy S25 battery is excellent.", "author": "reviewer", "created_utc": 1760000000, "permalink": "/r/test/comments/x/c1", "subreddit": "Android"}}]}}]),
    ])
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: next(responses))
    result = adapter.search("Samsung Galaxy S25", ["Samsung Galaxy S25"], SimpleNamespace(may_continue=lambda: True))
    records = adapter.normalize(result)
    assert records[0]["review_text"].startswith("Samsung Galaxy S25")
    assert records[0]["reviewer_name"] == "reviewer"
    assert adapter.provenance(result) == "Reddit public discussions via official OAuth API"


def test_reddit_adapter_requires_server_side_credentials():
    with pytest.raises(FallbackAdapterError) as exc:
        RedditOfficialDiscussionAdapter(None, None).validate_configuration()
    assert exc.value.status == "API_CREDENTIALS_REQUIRED"


def test_reddit_adapter_timeout_is_bounded(monkeypatch):
    adapter = _safe_adapter(monkeypatch)
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(FallbackAdapterError) as exc:
        adapter.search("Samsung Galaxy S25", ["Samsung Galaxy S25"], SimpleNamespace(may_continue=lambda: True))
    assert exc.value.status == "TIMEOUT"


def test_reddit_adapter_rejects_invalid_or_empty_responses(monkeypatch):
    adapter = _safe_adapter(monkeypatch)
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response(b"not-json"))
    with pytest.raises(FallbackAdapterError) as exc:
        adapter.search("Samsung Galaxy S25", ["Samsung Galaxy S25"], SimpleNamespace(may_continue=lambda: True))
    assert exc.value.status == "INVALID_RESPONSE"
    assert adapter.normalize({"threads": []}) == []


def test_reddit_irrelevant_and_duplicate_comments_follow_existing_ingestion_semantics(monkeypatch):
    adapter = _safe_adapter(monkeypatch)
    candidate = Candidate("reddit", "Reddit", "Official OAuth API", "https://www.reddit.com/dev/api/", "https://oauth.reddit.com", "discussion", status="APPROVED")
    class DuplicateAdapter(_Adapter):
        def normalize(self, response):
            return [
                {"review_text": "Samsung Galaxy S25 is excellent and reliable.", "rating": None},
                {"review_text": "Samsung Galaxy S25 is excellent and reliable.", "rating": None},
                {"review_text": "Galaxy S24 is unrelated.", "rating": None},
            ]
    result = run_fallback(_source(), "NO_SUPPORTED_ELEMENTS", ApprovedSourceRegistry([candidate], {"reddit": DuplicateAdapter()}))
    assert result.status == "SUCCESS"
    assert len(result.records) == 2  # records are retained; CollectionService flags duplicates.


def test_reddit_adapter_keeps_ssrf_validation_at_fixed_hosts(monkeypatch):
    from app.errors.exceptions import CollectionError
    adapter = RedditOfficialDiscussionAdapter("id", "secret")
    monkeypatch.setattr("app.services.source_fallback.validate_url_ssrf", lambda _url: (_ for _ in ()).throw(CollectionError("blocked", code="COLLECTION_SSRF_BLOCKED")))
    with pytest.raises(CollectionError) as exc:
        adapter.search("Samsung Galaxy S25", ["Samsung Galaxy S25"], SimpleNamespace(may_continue=lambda: True))
    assert exc.value.code == "COLLECTION_SSRF_BLOCKED"
