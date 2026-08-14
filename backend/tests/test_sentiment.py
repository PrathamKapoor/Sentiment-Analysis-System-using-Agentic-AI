from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_analyse_positive_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["This product is absolutely wonderful, I love it!"])

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    assert resp.status_code == 202
    assert resp.get_json()["data"]["analysedCount"] == 1

    results = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert results[0]["sentimentLabel"] == "positive"


def test_analyse_negative_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["This is terrible, worst purchase ever, I hate it."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    results = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert results[0]["sentimentLabel"] == "negative"


def test_analyse_neutral_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["It is a box."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    results = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert results[0]["sentimentLabel"] == "neutral"


def test_score_and_confidence_ranges_valid(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Great!", "Awful.", "It exists.", "Okay I guess, mixed feelings."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    results = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert len(results) == 4
    for r in results:
        assert 0 <= r["positiveScore"] <= 1
        assert 0 <= r["negativeScore"] <= 1
        assert 0 <= r["neutralScore"] <= 1
        assert 0 <= r["confidenceScore"] <= 1
        assert r["sentimentLabel"] in ("positive", "negative", "neutral")


def test_model_metadata_stored(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Nice."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    results = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert results[0]["modelName"] == "vader"
    assert results[0]["modelVersion"]


def test_batch_analysis(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    texts = [f"Review number {i} is pretty good." for i in range(25)]
    create_reviews_directly(project_id, texts)

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    assert resp.get_json()["data"]["analysedCount"] == 25

    summary = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment/summary", headers=headers).get_json()["data"]
    assert summary["analysedReviews"] == 25
    assert summary["totalReviews"] == 25


def test_reanalysis_updates_existing_result(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Fine."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    first = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"][0]

    # Second run with no new reviews shouldn't create a duplicate result.
    reanalyse_resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment/reanalyse", json={}, headers=headers)
    assert reanalyse_resp.status_code == 202
    second = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment", headers=headers).get_json()["data"]["items"]
    assert len(second) == 1
    assert second[0]["id"] == first["id"]


def test_skip_deleted_review(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["Deleted review text, great product!"])

    from app.extensions import db
    from datetime import datetime, timezone
    reviews[0].deleted_at = datetime.now(timezone.utc)
    db.session.commit()

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    assert resp.get_json()["data"]["analysedCount"] == 0


def test_skip_spam_review_by_default(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Spam review, buy now great deal!"], is_spam=True)

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    assert resp.get_json()["data"]["analysedCount"] == 0

    include_spam_resp = client.post(
        f"/api/v1/projects/{project_id}/analysis/sentiment", json={"includeSpam": True}, headers=headers
    )
    assert include_spam_resp.get_json()["data"]["analysedCount"] == 1


def test_skip_duplicates_by_default(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Duplicate flagged review."], is_duplicate=True)

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    assert resp.get_json()["data"]["analysedCount"] == 0

    include_dup_resp = client.post(
        f"/api/v1/projects/{project_id}/analysis/sentiment", json={"includeDuplicates": True}, headers=headers
    )
    assert include_dup_resp.get_json()["data"]["analysedCount"] == 1


def test_manual_correction(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["It is fine I suppose."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    resp = client.post(
        f"/api/v1/reviews/{reviews[0].id}/correct-sentiment",
        json={"label": "positive", "reason": "Reviewer meant it sarcastically-positive"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["sentimentLabel"] == "positive"
    assert body["isManuallyCorrected"] is True
    assert body["correctedByUserId"]

    sentiment_resp = client.get(f"/api/v1/reviews/{reviews[0].id}/sentiment", headers=headers)
    assert sentiment_resp.get_json()["data"]["sentimentLabel"] == "positive"


def test_manual_correction_writes_audit_log(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["Neutral text here."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    client.post(
        f"/api/v1/reviews/{reviews[0].id}/correct-sentiment",
        json={"label": "negative", "reason": "test reason"},
        headers=headers,
    )

    from app.models import AuditLog
    entries = AuditLog.query.filter_by(action="sentiment.corrected").all()
    assert len(entries) == 1
    assert entries[0].event_metadata["correctedLabel"] == "negative"
    assert entries[0].event_metadata["reason"] == "test reason"


def test_invalid_correction_label_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, ["Some text."])

    resp = client.post(
        f"/api/v1/reviews/{reviews[0].id}/correct-sentiment",
        json={"label": "extremely-positive"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_cross_organisation_analysis_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Text"])

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=other_headers)
    assert resp.status_code == 404


def test_unauthorised_user_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={})
    assert resp.status_code == 401
