from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_aspect_analysis_extracts_and_splits_local_sentiment(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, [
        "The design looks fantastic. The battery life is absolutely terrible."
    ])

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    assert resp.status_code == 202
    assert resp.get_json()["data"]["reviewsAnalysed"] == 1

    aspects = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    names = {a["name"]: a for a in aspects}
    assert "design" in names
    assert "battery" in names
    # Different local sentiment per aspect — not just the overall review score.
    assert names["design"]["positiveCount"] == 1
    assert names["battery"]["negativeCount"] == 1


def test_aspect_frequency_and_percentages(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, [
        "Delivery was late.",
        "Delivery was late again, very frustrating.",
        "Delivery arrived on time and I was happy.",
    ])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)

    aspects = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    delivery = next(a for a in aspects if a["name"] == "delivery")
    assert delivery["frequency"] == 3
    total_pct = delivery["positivePercentage"] + delivery["negativePercentage"] + delivery["neutralPercentage"]
    assert 99.0 <= total_pct <= 101.0


def test_reanalysis_does_not_duplicate(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["The price is way too high for what you get."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    first = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]

    reanalyse_resp = client.post(f"/api/v1/projects/{project_id}/analysis/aspects/reanalyse", json={}, headers=headers)
    assert reanalyse_resp.status_code == 202
    second = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    assert len(first) == len(second) == 1
    assert first[0]["frequency"] == second[0]["frequency"] == 1

    from app.models import Aspect
    assert Aspect.query.filter_by(project_id=project_id, name="price").count() == 1


def test_aspect_detail_and_related_reviews(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Packaging was damaged on arrival."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    aspect_id = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"][0]["id"]

    detail = client.get(f"/api/v1/projects/{project_id}/analysis/aspects/{aspect_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["frequency"] == 1

    reviews = client.get(f"/api/v1/projects/{project_id}/analysis/aspects/{aspect_id}/reviews", headers=headers)
    assert reviews.status_code == 200
    items = reviews.get_json()["data"]["items"]
    assert len(items) == 1
    assert "aspectSentiment" in items[0]
    assert items[0]["aspectSentiment"]["evidenceText"]


def test_review_level_aspects_endpoint(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["Great customer service but slow delivery."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)

    resp = client.get(f"/api/v1/reviews/{reviews[0].id}/aspects", headers=headers)
    assert resp.status_code == 200
    aspect_names = {a["aspectName"] for a in resp.get_json()["data"]["items"]}
    assert "customer service" in aspect_names
    assert "delivery" in aspect_names


def test_cross_project_aspect_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["The price is too high."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    aspect_id = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"][0]["id"]

    other_project_id = create_project(client, headers, name="Other Project")
    resp = client.get(f"/api/v1/projects/{other_project_id}/analysis/aspects/{aspect_id}", headers=headers)
    assert resp.status_code == 404


def test_cross_organisation_aspect_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["The price is too high."])

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=other_headers)
    assert resp.status_code == 404


def test_aspect_analysis_skips_spam_and_duplicates_by_default(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["The battery is bad."], is_spam=True)
    create_reviews_directly(project_id, ["The battery is bad."], is_duplicate=True)

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    assert resp.get_json()["data"]["reviewsAnalysed"] == 0
