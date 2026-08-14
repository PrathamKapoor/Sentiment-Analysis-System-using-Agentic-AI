from datetime import date

from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_keyword_frequencies_correct(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, [
        "The battery life is amazing.",
        "Battery life could be better.",
        "I love the battery on this device.",
    ])

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/keywords", headers=headers)
    assert resp.status_code == 200
    items = resp.get_json()["data"]["items"]
    battery = next(k for k in items if k["keyword"] == "battery")
    assert battery["frequency"] == 3


def test_stop_words_excluded(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["This is the best product that I have ever used."])

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/keywords", headers=headers)
    keywords = [k["keyword"] for k in resp.get_json()["data"]["items"]]
    for stopword in ("this", "the", "that", "have"):
        assert stopword not in keywords


def test_empty_corpus_handled(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/keywords", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["items"] == []

    cloud_resp = client.get(f"/api/v1/projects/{project_id}/analysis/word-cloud", headers=headers)
    assert cloud_resp.status_code == 200
    assert cloud_resp.get_json()["data"]["items"] == []


def test_keyword_filters_work(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Excellent packaging and delivery."], review_date=date(2026, 1, 1))
    create_reviews_directly(project_id, ["Terrible packaging experience overall."], review_date=date(2026, 6, 1))

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/keywords",
        query_string={"dateFrom": "2026-05-01"},
        headers=headers,
    )
    keywords = [k["keyword"] for k in resp.get_json()["data"]["items"]]
    assert "terrible" in keywords
    assert "excellent" not in keywords


def test_keyword_date_filter_rejects_invalid_date(client):
    _, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/keywords",
        query_string={"dateFrom": "not-a-date"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_word_cloud_shape(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Wonderful delivery experience, fast and reliable."])
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/word-cloud", headers=headers)
    items = resp.get_json()["data"]["items"]
    assert all({"text", "value", "sentiment"} <= set(item.keys()) for item in items)
