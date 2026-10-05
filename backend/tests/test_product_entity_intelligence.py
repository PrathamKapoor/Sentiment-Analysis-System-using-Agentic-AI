from tests.conftest import register, login, auth_header


def _owner_context(client, org_name="Entity Org", email="entity-owner@example.test"):
    registered = register(client, org_name=org_name, email=email).get_json()["data"]
    session = login(client, email=email).get_json()["data"]
    headers = {
        **auth_header(session["accessToken"]),
        "X-Organisation-Id": registered["organisationId"],
    }
    return headers


def _create_project(client, headers, name="Phone Project"):
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "productOrTopic": "Samsung Galaxy S25"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["data"]["id"]


def test_project_entity_round_trips_canonical_product_and_keyword_groups(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    payload = {
        "brand": "Samsung",
        "product": "Galaxy S25",
        "model": "S25",
        "sku": "SM-S931B",
        "canonicalUrl": "https://www.flipkart.com/samsung-galaxy-s25/p/itmexample",
        "aliases": ["Samsung S25", "Galaxy S25"],
        "identifiers": {"flipkartPid": "itmexample"},
        "includeKeywords": ["battery", "camera"],
        "excludeKeywords": ["case", "charger"],
        "securityKeywords": ["privacy", "account access"],
        "competitorKeywords": ["Pixel 10", "iPhone 17"],
        "customKeywords": ["Galaxy AI"],
    }

    saved = client.put(
        f"/api/v1/projects/{project_id}/entity", json=payload, headers=headers
    )
    assert saved.status_code == 200
    entity = saved.get_json()["data"]
    assert entity["canonicalName"] == "Samsung Galaxy S25"
    assert entity["sku"] == "SM-S931B"
    assert entity["aliases"] == ["Samsung S25", "Galaxy S25"]
    assert entity["includeKeywords"] == ["battery", "camera"]
    assert entity["securityKeywords"] == ["privacy", "account access"]

    loaded = client.get(f"/api/v1/projects/{project_id}/entity", headers=headers)
    assert loaded.status_code == 200
    assert loaded.get_json()["data"] == entity


def test_project_entity_rejects_malformed_identifier_values(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    response = client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"identifiers": {"pid": {"unsafe": "object"}}},
        headers=headers,
    )
    assert response.status_code == 400

    credential_url = client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "canonicalUrl": "https://user:secret@example.test/product"},
        headers=headers,
    )
    assert credential_url.status_code == 400
    assert "credentials" in credential_url.get_json()["error"]["message"].lower()


def test_project_entity_is_hidden_from_other_organisations(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    other_headers = _owner_context(
        client, org_name="Other Entity Org", email="other-entity@example.test"
    )
    assert client.get(
        f"/api/v1/projects/{project_id}/entity", headers=other_headers
    ).status_code == 404
    assert client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Changed"},
        headers=other_headers,
    ).status_code == 404


def test_entity_resolution_uses_canonical_name_aliases_and_safe_keywords(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={
            "brand": "Samsung",
            "product": "Galaxy S25",
            "model": "S25",
            "aliases": ["Samsung S25", "Galaxy S25"],
            "includeKeywords": ["battery", "camera"],
            "securityKeywords": ["privacy"],
        },
        headers=headers,
    )

    from app.models import Project
    from app.services.entity_resolver import resolve_project_entity

    project = Project.query.filter_by(id=project_id).first()
    resolved = resolve_project_entity(project)
    assert resolved["canonicalName"] == "Samsung Galaxy S25"
    assert "Galaxy S25" in resolved["aliases"]
    assert resolved["includeKeywords"] == ["battery", "camera"]
    assert resolved["securityKeywords"] == ["privacy"]


def test_canonical_name_appends_model_when_product_name_does_not_include_it(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "product": "Galaxy", "model": "S25 Ultra"},
        headers=headers,
    )

    from app.models import ProjectEntity

    entity = ProjectEntity.query.filter_by(project_id=project_id).first()
    assert entity.canonical_name == "Samsung Galaxy S25 Ultra"


def test_competitor_intelligence_requires_explicit_switching_evidence_and_scopes_reviews(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "product": "Galaxy S25", "competitorKeywords": ["Pixel 10"]},
        headers=headers,
    )
    from tests.conftest_project import create_reviews_directly

    create_reviews_directly(
        project_id,
        [
            "The Pixel 10 camera is better, so I am switching to Pixel 10 because the photos are clearer.",
            "Pixel 10 is mentioned here but I am not changing phones.",
        ],
    )
    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/competitors", headers=headers
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["summary"]["mentions"] == 2
    assert data["summary"]["switchingIntent"] == 1
    switching = next(item for item in data["items"] if item["switchingIntent"])
    assert switching["competitor"] == "Pixel 10"
    assert switching["evidence"][0]["text"] == "Pixel 10"
    assert switching["switchingEvidence"]
    assert switching["reviewId"]


def test_competitor_intelligence_hides_cross_organisation_reviews(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    other_headers = _owner_context(
        client, org_name="Other Competitor Org", email="other-competitor@example.test"
    )
    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/competitors", headers=other_headers
    )
    assert response.status_code == 404
    categories = client.get(
        f"/api/v1/projects/{project_id}/analysis/feedback-categories", headers=other_headers
    )
    assert categories.status_code == 404


def test_competitor_matching_excludes_ineligible_reviews_and_requires_same_sentence(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "competitorKeywords": ["Pixel 10"]},
        headers=headers,
    )
    from tests.conftest_project import create_reviews_directly

    reviews = create_reviews_directly(
        project_id,
        [
            "I am switching my provider. Pixel 10 looks interesting.",
            "I am switching to Pixel 10 because setup is easier.",
            "Spam says Pixel 10 is better.",
        ],
    )
    reviews[2].is_spam = True

    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/competitors", headers=headers
    )
    data = response.get_json()["data"]
    assert data["summary"]["mentions"] == 2
    assert data["summary"]["switchingIntent"] == 1
    assert all(item["reviewId"] != str(reviews[2].id) for item in data["items"])


def test_competitor_switching_signal_must_name_that_competitor_as_destination(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "competitorKeywords": ["Pixel 10", "iPhone 17"]},
        headers=headers,
    )
    from tests.conftest_project import create_reviews_directly

    create_reviews_directly(project_id, [
        "I am switching to iPhone 17, but the Pixel 10 camera looks nice.",
    ])
    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/competitors", headers=headers
    )
    items = response.get_json()["data"]["items"]
    assert {item["competitor"]: item["switchingIntent"] for item in items} == {
        "iPhone 17": True,
        "Pixel 10": False,
    }


def test_feedback_categories_return_exact_evidence_and_exclude_spam(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Samsung", "competitorKeywords": ["Pixel 10"]},
        headers=headers,
    )
    from tests.conftest_project import create_reviews_directly

    reviews = create_reviews_directly(project_id, [
        "The camera is excellent, but support is slow. Please add offline maps.",
        "Pixel 10 is better because I am switching.",
        "Scam spam says account takeover happened.",
    ])
    reviews[2].is_spam = True

    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/feedback-categories", headers=headers
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    camera = next(item for item in data["items"] if item["reviewId"] == str(reviews[0].id))
    categories = {entry["category"]: entry["evidence"][0]["text"] for entry in camera["categories"]}
    assert categories["PRAISE"] == "excellent"
    assert categories["SUPPORT"] == "support"
    assert categories["PERFORMANCE"] == "slow"
    assert categories["FEATURE_REQUEST"] == "Please add"
    assert data["summary"]["reviewsScanned"] == 2
    assert all(item["reviewId"] != str(reviews[2].id) for item in data["items"])


def test_feedback_categories_use_project_security_keywords_with_spans(client):
    headers = _owner_context(client)
    project_id = _create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/entity",
        json={"brand": "Example", "securityKeywords": ["token exposure"]},
        headers=headers,
    )
    from tests.conftest_project import create_reviews_directly

    review = create_reviews_directly(project_id, ["The token exposure report was ignored."])[0]
    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/feedback-categories", headers=headers
    )
    item = response.get_json()["data"]["items"][0]
    assert item["reviewId"] == str(review.id)
    security = next(category for category in item["categories"] if category["category"] == "SECURITY")
    assert security["evidence"] == [{"text": "token exposure", "sourceSpan": [4, 18]}]
