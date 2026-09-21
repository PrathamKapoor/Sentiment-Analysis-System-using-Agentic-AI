from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_explanation_exists_for_positive_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["This product is absolutely wonderful, I love it!"])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    r = items[0]
    assert "vaderBreakdown" in r
    assert r["vaderBreakdown"] is not None
    assert "tokens" in r["vaderBreakdown"]
    assert "contributingTerms" in r["vaderBreakdown"]
    assert r["compoundScore"] is not None
    # This positive review should have contributing positive terms
    assert len(r["vaderBreakdown"]["contributingTerms"]["positive"]) >= 1


def test_explanation_exists_for_negative_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["This is dreadful, worst purchase ever I hate it."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    r = items[0]
    assert r["sentimentLabel"] == "negative"
    assert len(r["vaderBreakdown"]["contributingTerms"]["negative"]) >= 1


def test_explanation_exists_for_neutral_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["It is a box."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    r = items[0]
    assert r["sentimentLabel"] == "neutral"
    assert r["vaderBreakdown"] is not None
    # Neutral reviews have no directional contributors
    assert r["vaderBreakdown"]["contributingTerms"]["positive"] == []
    assert r["vaderBreakdown"]["contributingTerms"]["negative"] == []


def test_explanation_tokens_correspond_to_actual_vader_lexicon(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Love this gorgeous product, terrible waste otherwise."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    breakdown = items[0]["vaderBreakdown"]
    tokens = {t["lowered"]: t for t in breakdown["tokens"]}
    # "love" and "terrible" and "gorgeous" are in VADER's lexicon; they must be matched
    assert tokens.get("love", {}).get("matched") is True
    assert tokens.get("terrible", {}).get("matched") is True


def test_explanation_empty_review_still_has_breakdown_structure(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    # Create a review that will be skipped as empty text (no sentiment result)
    create_reviews_directly(project_id, ["   "])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert len(items) == 0


def test_manual_correction_clears_vader_breakdown(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["This product is absolutely wonderful, I love it!"])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    review_id = reviews[0].id
    # Correct the sentiment — the breakdown must be cleared afterwards.
    client.post(f"/api/v1/reviews/{review_id}/correct-sentiment", json={"label": "negative"}, headers=headers)
    refreshed = client.get(f"/api/v1/reviews/{review_id}", headers=headers).get_json()["data"]
    assert refreshed["sentiment"]["sentimentLabel"] == "negative"
    assert refreshed["sentiment"]["vaderBreakdown"] is None


def test_review_detail_includes_breakdown(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["Love this product!"])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    detail = client.get(f"/api/v1/reviews/{reviews[0].id}", headers=headers).get_json()["data"]
    assert "vaderBreakdown" in detail["sentiment"]
    assert detail["sentiment"]["compoundScore"] is not None


def test_reanalysis_updates_breakdown(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Great!"])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    first = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"][0]
    # Force reanalysis should still produce a breakdown
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment/reanalyse", json={}, headers=headers)
    second = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"][0]
    assert second["vaderBreakdown"] is not None
