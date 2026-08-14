from tests.conftest_project import owner_context, create_project, create_reviews_directly

DELIVERY_REVIEWS = [
    "Delivery was late and the package arrived damaged.",
    "Shipping took forever, delivery delay was frustrating.",
    "The delivery driver was rude and the package was late again.",
]
SOUND_REVIEWS = [
    "The sound quality on these headphones is amazing and crisp.",
    "Audio quality is excellent, bass and sound are great.",
    "Sound quality blew me away, very impressed with the audio.",
]


def test_topic_analysis_succeeds(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS + SOUND_REVIEWS)

    resp = client.post(
        f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 2}, headers=headers
    )
    assert resp.status_code == 202
    assert resp.get_json()["data"]["topicCount"] == 2
    assert resp.get_json()["data"]["reviewsClustered"] == 6


def test_topics_stored_and_review_links_stored(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS + SOUND_REVIEWS)
    client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 2}, headers=headers)

    topics = client.get(f"/api/v1/projects/{project_id}/analysis/topics", headers=headers).get_json()["data"]["items"]
    assert len(topics) == 2
    total_reviews_linked = sum(t["reviewCount"] for t in topics)
    assert total_reviews_linked == 6

    first_topic_id = topics[0]["id"]
    detail = client.get(f"/api/v1/projects/{project_id}/analysis/topics/{first_topic_id}", headers=headers)
    assert detail.status_code == 200
    assert "sentimentDistribution" in detail.get_json()["data"]

    reviews_resp = client.get(f"/api/v1/projects/{project_id}/analysis/topics/{first_topic_id}/reviews", headers=headers)
    assert reviews_resp.status_code == 200
    assert len(reviews_resp.get_json()["data"]["items"]) == topics[0]["reviewCount"]


def test_relevance_score_valid(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS + SOUND_REVIEWS)
    client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 2}, headers=headers)

    from app.models import ReviewTopic
    links = ReviewTopic.query.all()
    assert len(links) == 6
    for link in links:
        assert link.relevance_score is None or (0 <= float(link.relevance_score) <= 1)


def test_duplicate_review_topic_mapping_prevented_by_schema(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    reviews = create_reviews_directly(project_id, DELIVERY_REVIEWS)
    client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 1}, headers=headers)

    from app.models import ReviewTopic, Topic
    from app.extensions import db
    topic = Topic.query.filter_by(project_id=project_id).first()
    link = ReviewTopic.query.filter_by(review_id=reviews[0].id, topic_id=topic.id).first()
    assert link is not None

    # Composite primary key (review_id, topic_id) is the duplicate-prevention
    # mechanism — inserting the same pair again must fail at the DB level.
    dup = ReviewTopic(review_id=reviews[0].id, topic_id=topic.id, relevance_score=0.5)
    db.session.add(dup)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_duplicate_cluster_names_disambiguated(client, monkeypatch):
    """Two clusters can legitimately produce identical top-terms names (tied/
    overlapping TF-IDF weights) — topics.uq_topic_project_name requires
    uniqueness within one run, so the service must disambiguate rather than
    let the second insert fail with an IntegrityError.
    """
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS + SOUND_REVIEWS)

    import app.services.topic_service as topic_service_module

    def fake_cluster(texts, k):
        n = len(texts)
        half = n // 2
        assignments = [0] * half + [1] * (n - half)
        topic_terms = {0: ["same", "terms", "here"], 1: ["same", "terms", "here"]}
        relevance = [0.5] * n
        return assignments, topic_terms, relevance

    monkeypatch.setattr(topic_service_module, "_cluster", fake_cluster)

    resp = client.post(
        f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 2}, headers=headers
    )
    assert resp.status_code == 202

    from app.models import Topic
    names = {t.name for t in Topic.query.filter_by(project_id=project_id).all()}
    assert len(names) == 2
    assert "same / terms / here" in names
    assert "same / terms / here (2)" in names


def test_small_dataset_handled_without_crashing(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Only one review here."])

    resp = client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_cross_project_topic_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS)
    client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={"topicCount": 1}, headers=headers)
    topic_id = client.get(f"/api/v1/projects/{project_id}/analysis/topics", headers=headers).get_json()["data"]["items"][0]["id"]

    other_project_id = create_project(client, headers, name="Other Project")
    resp = client.get(f"/api/v1/projects/{other_project_id}/analysis/topics/{topic_id}", headers=headers)
    assert resp.status_code == 404


def test_cross_organisation_topic_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, DELIVERY_REVIEWS)

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.post(f"/api/v1/projects/{project_id}/analysis/topics", json={}, headers=other_headers)
    assert resp.status_code == 404
