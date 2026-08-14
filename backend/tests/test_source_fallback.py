from types import SimpleNamespace

from app.services.source_fallback import (
    ApprovedSourceRegistry, Candidate, SourceAdapter, discover_candidates,
    discovery_queries, run_fallback,
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
