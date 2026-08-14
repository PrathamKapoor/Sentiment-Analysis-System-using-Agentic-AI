from pathlib import Path

import pytest

from app.errors.exceptions import CollectionError
from app.services.collectors.ecommerce import (
    AmazonIndiaAdapter,
    FlipkartAdapter,
    normalize_ecommerce_url,
)
from app.services.data_source_service import normalize_keywords
from tests.conftest_project import create_project, owner_context
from tests.test_collection import _FakeResponse, _mock_get, _mock_public_dns, _no_robots


FIXTURES = Path(__file__).parent / "fixtures" / "collection"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(("raw", "expected"), [
    (
        "https://www.amazon.in/Samsung-Galaxy-Ultra-Storage/dp/B0DSKL9MQ8/ref=sr_1_1?tag=affiliate&qid=1",
        "https://www.amazon.in/dp/B0DSKL9MQ8",
    ),
    (
        "https://amazon.in/gp/product/b0dskl9mq8?ref_=abc",
        "https://www.amazon.in/dp/B0DSKL9MQ8",
    ),
    (
        "https://www.flipkart.com/example-phone/p/itm7d0e1ef71672e?pid=MOB123&lid=LST123&otracker=search",
        "https://www.flipkart.com/example-phone/p/itm7d0e1ef71672e?pid=MOB123&lid=LST123",
    ),
])
def test_ecommerce_url_normalization_preserves_identity(raw, expected):
    assert normalize_ecommerce_url(raw) == expected


def test_amazon_identity_is_stable_and_invalid_shapes_are_rejected():
    adapter = AmazonIndiaAdapter()
    assert adapter.product_identity("https://www.amazon.in/dp/B0DSKL9MQ8") == "B0DSKL9MQ8"
    assert adapter.product_identity("https://www.amazon.in/example?asin=B0DSKL9MQ8") is None
    with pytest.raises(CollectionError) as error:
        adapter.review_url("https://www.amazon.in/example")
    assert error.value.code == "COLLECTION_UNSUPPORTED_SOURCE"


def test_amazon_review_link_is_discovered_from_product_page():
    adapter = AmazonIndiaAdapter()
    discovered = adapter.discover_review_url(
        fixture("amazon_product.html"), "https://www.amazon.in/dp/B0DSKL9MQ8",
    )
    assert discovered == (
        "https://www.amazon.in/Samsung-Galaxy-S25-Ultra/product-reviews/"
        "B0DSKL9MQ8?reviewerType=all_reviews"
    )


def test_amazon_fixture_extracts_reviews_with_optional_fields():
    adapter = AmazonIndiaAdapter()
    records, candidates, title = adapter.extract(fixture("amazon_reviews.html"), 10)
    assert candidates == 2
    assert len(records) == 2
    assert records[0]["rating"] == 5.0
    assert records[0]["source_metadata"]["title"] == "Excellent camera"
    assert records[1]["rating"] is None
    assert records[1]["review_text"] == "Display is bright, but the phone is heavy."
    assert "Customer reviews" in title


def test_flipkart_fixture_extracts_reviews_with_optional_fields():
    adapter = FlipkartAdapter()
    records, candidates, _title = adapter.extract(fixture("flipkart_reviews.html"), 10)
    assert candidates == 2
    assert [record["rating"] for record in records] == [5.0, 3.0]
    assert records[0]["reviewer_name"] == "Meera"
    assert records[1]["source_metadata"]["title"] is None


def test_current_flipkart_markup_extracts_multiple_review_cards_without_selector_duplicates():
    adapter = FlipkartAdapter()
    records, candidates, title = adapter.extract(fixture("flipkart_current_reviews.html"), 20)

    assert candidates == 3  # malformed fourth card is ignored
    assert len(records) == 3
    assert "Flipkart.com" in title
    assert records[0]["source_metadata"]["title"] == "Just wow!"
    assert records[0]["review_text"] == "Overall Excellent phone"
    assert records[0]["rating"] == 5.0
    assert records[0]["reviewer_name"] == "Sourav Kumar"
    assert records[1]["source_metadata"]["title"] == "Terrific"
    assert records[1]["review_text"] == "Excellent Product...I just loved it"
    assert records[1]["rating"] == 4.0
    assert records[1]["reviewer_name"] is None
    assert records[2]["review_text"] == "Mind-blowing purchase"
    assert records[2]["rating"] is None
    assert len({(record["source_metadata"].get("title"), record["review_text"]) for record in records}) == 3


def test_block_page_is_distinct_from_no_reviews():
    assert AmazonIndiaAdapter().is_blocked(fixture("amazon_blocked.html")) is True
    assert AmazonIndiaAdapter().is_blocked("<html><body><p>No reviews yet.</p></body></html>") is False


def test_malformed_or_selector_changed_html_is_safe_zero_candidates():
    records, candidates, _title = FlipkartAdapter().extract("<html><div class='unknown'>unfinished", 10)
    assert records == []
    assert candidates == 0


def test_site_adapters_discover_public_pagination_links():
    amazon_next = AmazonIndiaAdapter().next_page(
        "<li class='a-last'><a href='/product-reviews/B0DSKL9MQ8?pageNumber=2'>Next page</a></li>",
        "https://www.amazon.in/product-reviews/B0DSKL9MQ8",
    )
    flipkart_next = FlipkartAdapter().next_page(
        "<a href='/example/product-reviews/itm123?page=2'>Next</a>",
        "https://www.flipkart.com/example/product-reviews/itm123",
    )
    assert amazon_next.endswith("pageNumber=2")
    assert flipkart_next.endswith("page=2")


def test_keyword_normalization_is_case_insensitive_any_scope_not_all_required():
    keywords = normalize_keywords([
        " Battery ", "camera", "battery", "CAMERA", "Galaxy AI, display", "", ",,",
    ])
    assert keywords == ["Battery", "camera", "Galaxy AI", "display"]
    review = "The camera quality is excellent."
    assert any(keyword.casefold() in review.casefold() for keyword in keywords)
    assert not all(keyword.casefold() in review.casefold() for keyword in keywords)


@pytest.mark.parametrize(("raw", "expected"), [
    ([], []),
    (["camera"], ["camera"]),
    (["camera", "Camera", " battery, display ", ""], ["camera", "battery", "display"]),
])
def test_empty_single_and_many_keyword_lists_are_normalized(raw, expected):
    assert normalize_keywords(raw) == expected


@pytest.mark.parametrize(("source_url", "review_path", "product_fixture", "review_fixture", "adapter"), [
    ("https://www.amazon.in/dp/B0DSKL9MQ8?tag=tracking", "/product-reviews/B0DSKL9MQ8", "amazon_product.html", "amazon_reviews.html", "amazon_india"),
    ("https://www.flipkart.com/example-phone/p/itm7d0e1ef71672e?pid=MOB123&otracker=search", "/product-reviews/itm7d0e1ef71672e", "flipkart_product.html", "flipkart_reviews.html", "flipkart"),
])
def test_product_url_discovers_review_page_and_reports_stage_counts(
    client, monkeypatch, source_url, review_path, product_fixture, review_fixture, adapter,
):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={
            "type": "ecommerce", "url": source_url,
            "keywords": ["battery", "camera", "display", "performance", "unmatched term"],
        },
        headers=headers,
    )
    assert response.status_code == 201
    source = response.get_json()["data"]
    source_id = source["id"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in", "flipkart.com", "www.flipkart.com"})

    requested = []

    def responder(url):
        requested.append(url)
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        if review_path in url:
            return _FakeResponse(html=fixture(review_fixture))
        return _FakeResponse(html=fixture(product_fixture))

    _mock_get(monkeypatch, responder)
    collected = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert collected.status_code == 200
    result = collected.get_json()["data"]
    assert result["adapter"] == adapter
    assert result["fetchStatus"] == "success"
    assert result["candidateItemsFound"] == 2
    assert result["itemsParsed"] == 2
    assert result["itemsAfterFilter"] == 2
    assert result["itemsSaved"] == 2
    assert result["resultCode"] == "COLLECTION_SUCCESS"
    assert result["productPageStatus"] == "SUCCESS"
    assert result["productPageHttpStatus"] == 200
    assert result["reviewPageStatus"] == "SUCCESS"
    assert result["reviewPageHttpStatus"] == 200
    assert result["reviewDiscoveryMethod"] == "product_page_link"
    assert result["parserStatus"] == "SUCCESS"
    assert any(review_path in url for url in requested)


def test_product_page_404_identifies_the_failing_stage(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "ecommerce", "url": "https://www.amazon.in/dp/B0DSKL9MQ8"},
        headers=headers,
    ).get_json()["data"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in"})
    _mock_get(monkeypatch, lambda url: _no_robots(url) if url.endswith("/robots.txt") else _FakeResponse(status_code=404))

    response = client.post(f"/api/v1/sources/{source['id']}/collect", headers=headers)
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "COLLECTION_HTTP_ERROR"
    assert error["details"]["productPageStatus"] == "HTTP_404"
    assert error["details"]["reviewPageStatus"] is None


def test_review_page_404_preserves_successful_product_stage(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "ecommerce", "url": "https://www.amazon.in/dp/B0DSKL9MQ8"},
        headers=headers,
    ).get_json()["data"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        if "/product-reviews/" in url:
            return _FakeResponse(status_code=404)
        return _FakeResponse(html=fixture("amazon_product.html"))

    _mock_get(monkeypatch, responder)
    response = client.post(f"/api/v1/sources/{source['id']}/collect", headers=headers)
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "COLLECTION_HTTP_ERROR"
    assert error["details"]["productPageStatus"] == "SUCCESS"
    assert error["details"]["productPageHttpStatus"] == 200
    assert error["details"]["reviewPageStatus"] == "HTTP_404"
    assert error["details"]["reviewDiscoveryMethod"] == "product_page_link"


def test_source_health_check_reports_product_and_review_pipeline(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "ecommerce", "url": "https://www.amazon.in/dp/B0DSKL9MQ8"},
        headers=headers,
    ).get_json()["data"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=fixture("amazon_reviews.html") if "/product-reviews/" in url else fixture("amazon_product.html"))

    _mock_get(monkeypatch, responder)
    response = client.post(f"/api/v1/sources/{source['id']}/test-connection", headers=headers)
    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["platform"] == "Amazon India"
    assert result["adapterClass"] == "AmazonIndiaAdapter"
    assert result["productIdentity"] == "B0DSKL9MQ8"
    assert result["productPage"]["httpStatus"] == 200
    assert result["reviewPage"]["httpStatus"] == 200
    assert result["reviewCandidatesDetected"] == 2


def test_flipkart_review_page_robots_policy_stops_after_product_fetch(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={
            "type": "ecommerce",
            "url": "https://www.flipkart.com/example-phone/p/itm7d0e1ef71672e?pid=MOB123",
        },
        headers=headers,
    ).get_json()["data"]
    _mock_public_dns(monkeypatch, {"flipkart.com", "www.flipkart.com"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _FakeResponse(html="User-agent: *\nDisallow: /example-phone/product-reviews/")
        return _FakeResponse(html=fixture("flipkart_product.html"))

    _mock_get(monkeypatch, responder)
    response = client.post(f"/api/v1/sources/{source['id']}/collect", headers=headers)
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "COLLECTION_NOT_PERMITTED"
    assert error["details"]["adapter"] == "flipkart"
    assert error["details"]["productPageStatus"] == "SUCCESS"
    assert error["details"]["reviewPageStatus"] is None
    assert error["details"]["parserStatus"] == "NOT_REACHED"


def test_flipkart_preview_returns_current_review_text_without_persisting(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={
            "type": "ecommerce",
            "url": "https://www.flipkart.com/example-phone/p/itm7d0e1ef71672e?pid=MOB123",
            "keywords": ["camera", "battery"],
        },
        headers=headers,
    ).get_json()["data"]
    _mock_public_dns(monkeypatch, {"flipkart.com", "www.flipkart.com"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        if "/product-reviews/" in url:
            return _FakeResponse(html=fixture("flipkart_current_reviews.html"))
        return _FakeResponse(html=fixture("flipkart_product.html"))

    _mock_get(monkeypatch, responder)
    preview = client.post(f"/api/v1/sources/{source['id']}/preview", json={}, headers=headers)
    assert preview.status_code == 200
    data = preview.get_json()["data"]
    assert data["candidateItemsFound"] == 3
    assert data["detectedRecordCountEstimate"] == 3
    assert data["parserStatus"] == "SUCCESS"
    assert data["keywordFilteringStatus"] == "NOT_APPLIED_DURING_PREVIEW"
    assert data["sampleRecords"][0]["source_metadata"]["title"] == "Just wow!"
    assert data["sampleRecords"][0]["review_text"] == "Overall Excellent phone"

    reviews = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers)
    assert reviews.status_code == 200
    assert reviews.get_json()["data"]["items"] == []


def test_successful_fetch_with_no_selector_has_explicit_reason(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "ecommerce", "url": "https://www.amazon.in/dp/B0DSKL9MQ8"},
        headers=headers,
    )
    source_id = response.get_json()["data"]["id"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in"})

    def responder(url):
        return _no_robots(url) if url.endswith("/robots.txt") else _FakeResponse(html="<html><p>No reviews here.</p></html>")

    _mock_get(monkeypatch, responder)
    result = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers).get_json()["data"]
    assert result["status"] == "no_records"
    assert result["candidateItemsFound"] == 0
    assert result["resultCode"] == "FALLBACK_CREDENTIALS_REQUIRED"
    assert result["fallback"]["terminalStatus"] == "API_CREDENTIALS_REQUIRED"
    assert "server-side api credentials" in result["resultMessage"].lower()


def test_challenge_page_returns_structured_blocked_error(client, monkeypatch):
    _org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "ecommerce", "url": "https://www.amazon.in/dp/B0DSKL9MQ8"},
        headers=headers,
    )
    source_id = response.get_json()["data"]["id"]
    _mock_public_dns(monkeypatch, {"amazon.in", "www.amazon.in"})

    def responder(url):
        return _no_robots(url) if url.endswith("/robots.txt") else _FakeResponse(html=fixture("amazon_blocked.html"))

    _mock_get(monkeypatch, responder)
    response = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "COLLECTION_BLOCKED"
    assert error["details"]["fetchStatus"] == "blocked"
    assert error["details"]["adapter"] == "amazon_india"
