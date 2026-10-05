import json
from types import SimpleNamespace

from app.services.product_discovery import (
    deterministic_discovery,
    discover_product_terms,
    match_product_identity,
    parse_discovery_output,
)
from app.services.scraping_providers import normalize_provider_records
from app.services.scraping_providers import _provider_source_url
from app.services import collection_pipeline
from app.models import DataSource
from app.extensions import db
from tests.conftest_project import owner_context, create_project


def test_product_discovery_requires_strict_json_and_keeps_user_canonical_name():
    output = json.dumps({
        "canonical_name": "Samsung Galaxy S24 Ultra",
        "brand": "Samsung",
        "product": "Galaxy S24",
        "model": "S24",
        "aliases": ["Samsung S24"],
        "search_keywords": ["Samsung Galaxy S24 review"],
        "identity_constraints": ["Samsung", "S24"],
        "exclude_keywords": ["Ultra", "FE"],
        "include_keywords": ["Samsung Galaxy S24"],
        "security_keywords": ["unauthorized access"],
        "competitor_keywords": ["Pixel 10"],
        "custom_keywords": ["Galaxy AI"],
        "identifiers": {"asin": "B0ABCDEF12"},
    })

    parsed = parse_discovery_output(output, "Samsung Galaxy S24", known_identifiers={"asin": "B0ABCDEF12"})

    assert parsed["canonical_name"] == "Samsung Galaxy S24"
    assert parsed["model"] == "S24"
    assert "Samsung Galaxy S24 review" in parsed["search_keywords"]
    assert parsed["include_keywords"] == ["Samsung Galaxy S24"]
    assert parsed["security_keywords"] == ["unauthorized access"]
    assert parsed["competitor_keywords"] == ["Pixel 10"]
    assert parsed["custom_keywords"] == ["Galaxy AI"]
    assert parsed["identifiers"] == {"asin": "B0ABCDEF12"}


def test_product_discovery_drops_identifiers_not_present_in_known_inputs():
    output = json.dumps({
        "canonical_name": "Samsung Galaxy S24", "brand": "Samsung", "product": "Galaxy", "model": "S24",
        "aliases": [], "search_keywords": ["Samsung Galaxy S24 review"], "identity_constraints": ["S24"],
        "exclude_keywords": [], "include_keywords": [], "security_keywords": [],
        "competitor_keywords": [], "custom_keywords": [],
        "identifiers": {"asin": "B0MODELMADEUP", "sku": "KNOWN-SKU"},
    })
    parsed = parse_discovery_output(output, "Samsung Galaxy S24", known_identifiers={"sku": "KNOWN-SKU"})
    assert parsed["identifiers"] == {"sku": "KNOWN-SKU"}


def test_llm_discovery_receives_known_identifiers_and_returns_reviewable_groups():
    from app.services.llm.provider import LLMResult

    class Provider:
        name = "openrouter"
        model = "poolside/laguna-s-2.1:free"
        prompt = ""
        def is_available(self): return True
        def complete(self, prompt, **_kwargs):
            self.prompt = prompt
            payload = {
                "canonical_name": "Samsung Galaxy S24", "brand": "Samsung", "product": "Galaxy",
                "model": "S24", "aliases": ["Samsung S24"],
                "search_keywords": ["Samsung Galaxy S24 review"], "identity_constraints": ["S24"],
                "include_keywords": ["Samsung Galaxy S24"], "exclude_keywords": ["Ultra"],
                "security_keywords": ["unauthorized access"], "competitor_keywords": ["Pixel 10"],
                "custom_keywords": ["Galaxy AI"],
                "identifiers": {"sku": "SM-S921B", "asin": "B0ABCDEF12"},
            }
            return LLMResult(text=json.dumps(payload), provider=self.name, model=self.model, status="ok")

    provider = Provider()
    result = discover_product_terms(
        "Samsung Galaxy S24", providers=[("main", provider)], sku="SM-S921B",
        canonical_url="https://www.amazon.in/dp/B0ABCDEF12",
    )
    assert '"sku": "SM-S921B"' in provider.prompt
    assert '"asin": "B0ABCDEF12"' in provider.prompt
    assert result["include_keywords"] == ["Samsung Galaxy S24"]
    assert result["security_keywords"] == ["unauthorized access"]
    assert result["competitor_keywords"] == ["Pixel 10"]
    assert result["custom_keywords"] == ["Galaxy AI"]
    assert result["identifiers"] == {"sku": "SM-S921B", "asin": "B0ABCDEF12"}


def test_invalid_or_extra_llm_fields_are_rejected():
    assert parse_discovery_output('{"canonical_name":"x","url":"https://evil.test"}', "Samsung S24") is None
    assert parse_discovery_output("not json", "Samsung S24") is None


def test_invalid_main_llm_output_fails_over_to_fallback_provider():
    from app.services.llm.provider import LLMResult

    class Provider:
        name = "fake-provider"
        model = "fake-model"
        def __init__(self, response): self.response, self.calls = response, 0
        def is_available(self): return True
        def complete(self, *_args, **_kwargs):
            self.calls += 1
            return LLMResult(text=self.response, provider="fake", model="fake-model", status="ok")

    main = Provider("not-json")
    fallback = Provider(json.dumps({
        "canonical_name": "wrong product", "brand": "Samsung", "product": "Galaxy", "model": "S24",
        "aliases": ["Samsung S24"], "search_keywords": ["Samsung S24 review"],
        "identity_constraints": ["Samsung", "S24"], "exclude_keywords": [],
        "include_keywords": [], "security_keywords": [], "competitor_keywords": [], "custom_keywords": [],
        "identifiers": {},
    }))
    result = discover_product_terms("Samsung Galaxy S24", providers=[("main", main), ("fallback", fallback)])
    assert main.calls == fallback.calls == 1
    assert result["provider_role"] == "fallback"
    assert result["canonical_name"] == "Samsung Galaxy S24"


def test_deterministic_discovery_keeps_input_as_canonical_identity():
    result = deterministic_discovery("Samsung Galaxy S24")
    assert result["canonical_name"] == "Samsung Galaxy S24"
    assert "Samsung Galaxy S24" in result["search_keywords"]


def test_provider_request_url_strips_credentials_query_and_fragment():
    assert _provider_source_url("https://alice:secret@example.test/product?token=private#section") == "https://example.test/product"


def test_exact_product_match_is_verified_and_variant_is_rejected():
    entity = {"canonicalName": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24", "aliases": []}

    exact = match_product_identity(entity, {"title": "Samsung Galaxy S24 Smartphone"})
    variant = match_product_identity(entity, {"title": "Samsung Galaxy S24 Ultra Smartphone"})

    assert exact["matched"] is True
    assert exact["status"] == "verified"
    assert exact["confidence"] == 0.95
    assert variant["matched"] is False
    assert variant["status"] == "rejected"


def test_ambiguous_identity_is_uncertain_and_not_accepted():
    result = match_product_identity(
        {"canonicalName": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24", "aliases": []},
        {"title": "Phone review", "review_text": "Battery is great"},
    )
    assert result["matched"] is False
    assert result["status"] == "uncertain"


def test_scraping_provider_normalization_requires_review_text_and_identity_match():
    entity = {"canonicalName": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24", "aliases": []}
    payload = {"reviews": [
        {"review": "Battery life is excellent.", "title": "Samsung Galaxy S24 review", "id": "r1"},
        {"review": "This is about a different model.", "title": "Samsung Galaxy S24 Ultra", "id": "r2"},
        {"title": "Samsung Galaxy S24", "id": "r3"},
    ]}

    records = normalize_provider_records(payload, entity, "https://www.amazon.in/dp/example")

    assert len(records) == 1
    assert records[0]["review_text"] == "Battery life is excellent."
    assert records[0]["external_review_id"] == "r1"
    assert records[0]["source_metadata"]["identityMatch"]["status"] == "verified"


def test_scraping_provider_does_not_infer_review_text_from_product_description():
    records = normalize_provider_records(
        {"product": {"title": "Samsung Galaxy S24", "description": "A smartphone description."}},
        {"canonicalName": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24", "aliases": []},
        "https://www.amazon.in/dp/example",
    )
    assert records == []


def test_rapidapi_provider_normalizes_records_without_exposing_key(client, monkeypatch):
    from contextlib import nullcontext
    from app.services.scraping_providers import RapidAPIScrapingProvider
    import app.services.scraping_providers as module

    with client.application.app_context():
        source = _pipeline_source(client)
        captured = {}

        class Response:
            status_code = 200
            def iter_content(self, _size):
                yield json.dumps({"reviews": [{"id": "review-1", "review": "Battery is excellent.",
                    "product_title": "Samsung Galaxy S24", "rating": "5", "url": "https://amazon.in/review/1"}]}).encode()
            def close(self): pass

        def fake_get(url, **kwargs):
            captured.update({"url": url, **kwargs})
            return Response()

        monkeypatch.setattr(module, "validate_url_ssrf", lambda _url: None)
        monkeypatch.setattr(module, "ssrf_safe_connections", nullcontext)
        monkeypatch.setattr(module.requests, "get", fake_get)
        provider = RapidAPIScrapingProvider(
            api_key="api-secret", host="reviews.example.test", base_url="https://reviews.example.test",
            endpoint="/reviews", source_types="ecommerce", timeout=2, max_results=10,
        )
        result = provider.collect(source, {"canonicalName": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24"}, ["Samsung Galaxy S24"])

    assert result.status == "success"
    assert result.records[0]["source_metadata"]["collection"]["level"] == 2
    assert captured["headers"]["X-RapidAPI-Key"] == "api-secret"
    assert captured["params"]["url"] == "https://www.amazon.in/dp/B012345678"
    assert "api-secret" not in repr(result)


def test_rapidapi_authentication_failure_is_safe(client, monkeypatch):
    from contextlib import nullcontext
    from app.services.scraping_providers import RapidAPIScrapingProvider
    import app.services.scraping_providers as module

    with client.application.app_context():
        source = _pipeline_source(client)
        class Response:
            status_code = 401
            def close(self): pass
        monkeypatch.setattr(module, "validate_url_ssrf", lambda _url: None)
        monkeypatch.setattr(module, "ssrf_safe_connections", nullcontext)
        monkeypatch.setattr(module.requests, "get", lambda *_a, **_kw: Response())
        provider = RapidAPIScrapingProvider(api_key="secret", host="api.example.test",
            base_url="https://api.example.test", endpoint="/reviews", source_types="ecommerce")
        result = provider.collect(source, {"canonicalName": "Samsung Galaxy S24"}, ["Samsung Galaxy S24"])
    assert result.status == "authentication_failed"
    assert "secret" not in repr(result)


def test_product_discovery_endpoint_is_project_authorized_and_does_not_save_llm_output(client):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.application.config["PRODUCT_DISCOVERY_LLM_ENABLED"] = False
    response = client.post(f"/api/v1/projects/{project_id}/entity/discover", json={
        "description": "Samsung Galaxy S24", "sku": "SM-S921B",
        "canonicalUrl": "https://www.amazon.in/dp/B0ABCDEF12",
    }, headers=headers)
    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["canonicalName"] == "Samsung Galaxy S24"
    assert result["includeKeywords"] == []
    assert result["securityKeywords"] == []
    assert result["competitorKeywords"] == []
    assert result["customKeywords"] == []
    assert result["identifiers"] == {"sku": "SM-S921B", "asin": "B0ABCDEF12"}
    stored = client.get(f"/api/v1/projects/{project_id}/entity", headers=headers).get_json()["data"]
    assert stored["canonicalName"] != "Samsung Galaxy S24" or stored["brand"] is None

    _other_org, other_headers = owner_context(client, org_name="Other Discovery Org", email="discovery-other@example.test")
    assert client.post(f"/api/v1/projects/{project_id}/entity/discover", json={"description": "Samsung Galaxy S24"}, headers=other_headers).status_code == 404


def _pipeline_source(client):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.put(f"/api/v1/projects/{project_id}/entity", json={
        "brand": "Samsung", "product": "Galaxy S24", "model": "S24",
    }, headers=headers)
    source_response = client.post(f"/api/v1/projects/{project_id}/sources", json={
        "type": "ecommerce", "url": "https://www.amazon.in/dp/B012345678",
    }, headers=headers)
    source_id = source_response.get_json()["data"]["id"]
    return db.session.get(DataSource, source_id)


def test_pipeline_stops_after_direct_evidence(client, monkeypatch):
    with client.application.app_context():
        source = _pipeline_source(client)
        monkeypatch.setattr(collection_pipeline, "configured_scraping_providers", lambda: (_ for _ in ()).throw(AssertionError("level 2 ran")))
        result = collection_pipeline.collect_with_fallbacks(
            source, [{"review_text": "The battery lasts all day."}], "SUCCESS",
            settings={"COLLECTION_MAX_LEVEL": 3, "COLLECTION_SCRAPING_ENABLED": True},
        )
    assert result.final_level == 1
    assert result.attempts == [{"level": 1, "method": "direct", "status": "success", "recordCount": 1}]
    assert result.records[0]["source_metadata"]["collection"]["method"] == "direct"


def test_pipeline_uses_scraping_provider_only_after_direct_returns_no_records(client):
    with client.application.app_context():
        source = _pipeline_source(client)

        class Scraper:
            def supports(self, _source): return True
            def collect(self, _source, _entity, _terms):
                return SimpleNamespace(status="success", provider="test-provider", reason="", duration_ms=4,
                    records=[{"review_text": "Battery life is excellent.", "source_metadata": {"productTitle": "Samsung Galaxy S24"}}])

        result = collection_pipeline.collect_with_fallbacks(
            source, [], "NO_RECORDS", settings={"COLLECTION_MAX_LEVEL": 3, "COLLECTION_SCRAPING_ENABLED": True},
            scraping_providers=[Scraper()],
        )
    assert result.final_level == 2
    assert [item["level"] for item in result.attempts] == [1, 2]
    assert result.records[0]["source_metadata"]["collection"]["provider"] == "test-provider"


def test_direct_timeout_invokes_level_two_and_persists_only_matched_evidence(client, monkeypatch):
    from app.errors.exceptions import CollectionError
    from app.models import Review
    import app.services.collection_service as collection_service

    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.put(f"/api/v1/projects/{project_id}/entity", json={
        "brand": "Samsung", "product": "Galaxy S24", "model": "S24",
    }, headers=headers)
    source_id = client.post(f"/api/v1/projects/{project_id}/sources", json={
        "type": "ecommerce", "url": "https://www.amazon.in/dp/B012345678",
    }, headers=headers).get_json()["data"]["id"]

    class Direct:
        collector_type = "test-direct"
        def validate_source(self, _source): pass
        def collect(self, *_args): raise CollectionError("Timed out safely.", code="COLLECTION_TIMEOUT")

    class Scraper:
        name = "test-provider"
        def supports(self, _source): return True
        def collect(self, *_args):
            return SimpleNamespace(status="success", provider=self.name, reason="", duration_ms=1,
                records=[{"review_text": "Battery lasts all day.", "source_metadata": {"productTitle": "Samsung Galaxy S24"}}])

    monkeypatch.setattr(collection_service, "_policy_for", lambda *_args: "allowed")
    monkeypatch.setattr(collection_service, "_require_collector", lambda *_args: Direct())
    monkeypatch.setattr(collection_pipeline, "configured_scraping_providers", lambda: [Scraper()])
    response = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["recordsInserted"] == 1
    assert [item["level"] for item in body["collectionPipeline"]] == [1, 2]
    with client.application.app_context():
        saved = Review.query.filter_by(project_id=project_id).one()
        assert saved.source_metadata["collection"]["level"] == 2
        assert saved.source_metadata["identityMatch"]["status"] == "verified"


def test_level_three_uses_discovery_terms_only_with_approved_retrieval(client, monkeypatch):
    with client.application.app_context():
        source = _pipeline_source(client)
        captured = {}

        def fallback(_source, _status, _registry, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(status="SUCCESS", records=[{"review_text": "Battery life is excellent.", "source_metadata": {"productTitle": "Samsung Galaxy S24"}}],
                                   provenance={"apiProvider": "approved-test-api"})

        monkeypatch.setattr(collection_pipeline, "run_fallback", fallback)
        result = collection_pipeline.collect_with_fallbacks(
            source, [], "NO_RECORDS", settings={"COLLECTION_MAX_LEVEL": 3, "COLLECTION_SCRAPING_ENABLED": False,
                "PRODUCT_DISCOVERY_LLM_ENABLED": True, "COLLECTION_LLM_FALLBACK_ENABLED": True},
            scraping_providers=[],
            discovery=lambda _name: {"search_keywords": ["Samsung S24 battery review"], "provider": "fake", "provider_role": "main", "model_name": "fake-model", "status": "ok"},
        )
    assert result.final_level == 3
    assert captured["search_terms"][0] == "Samsung S24 battery review"
    assert result.fallback.provenance["collectionLevel"] == 3
    assert result.attempts[-1]["method"] == "llm_assisted_approved_retrieval"
