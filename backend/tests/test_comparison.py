from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_compare_two_projects(client):
    org_id, headers = owner_context(client)
    project_a = create_project(client, headers, name="Brand A")
    project_b = create_project(client, headers, name="Brand B")

    create_reviews_directly(project_a, ["Amazing quality, I love it!", "Great product overall."])
    create_reviews_directly(project_b, ["Terrible quality, very disappointed.", "Delivery was late too."])
    client.post(f"/api/v1/projects/{project_a}/analysis/sentiment", json={}, headers=headers)
    client.post(f"/api/v1/projects/{project_b}/analysis/sentiment", json={}, headers=headers)

    resp = client.post(
        f"/api/v1/projects/{project_a}/analysis/comparison",
        json={"targetProjectIds": [project_a, project_b]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert len(body["entities"]) == 2
    entities_by_id = {e["projectId"]: e for e in body["entities"]}
    assert entities_by_id[project_a]["positivePercentage"] > entities_by_id[project_b]["positivePercentage"]
    assert body["narrative"] is not None
    assert "Brand A" in body["narrative"]


def test_compare_requires_at_least_two_targets(client):
    org_id, headers = owner_context(client)
    project_a = create_project(client, headers)

    resp = client.post(
        f"/api/v1/projects/{project_a}/analysis/comparison",
        json={"targetProjectIds": [project_a]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_compare_missing_project_not_found(client):
    org_id, headers = owner_context(client)
    project_a = create_project(client, headers)
    import uuid

    resp = client.post(
        f"/api/v1/projects/{project_a}/analysis/comparison",
        json={"targetProjectIds": [project_a, str(uuid.uuid4())]},
        headers=headers,
    )
    assert resp.status_code == 404


def test_compare_rejects_cross_organisation_project(client):
    org_id, headers = owner_context(client)
    project_a = create_project(client, headers)

    other_org_id, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    project_b = create_project(client, other_headers, name="Other Project")

    resp = client.post(
        f"/api/v1/projects/{project_a}/analysis/comparison",
        json={"targetProjectIds": [project_a, project_b]},
        headers=headers,
    )
    assert resp.status_code == 404


def test_compare_handles_no_analysed_data_gracefully(client):
    org_id, headers = owner_context(client)
    project_a = create_project(client, headers, name="Empty A")
    project_b = create_project(client, headers, name="Empty B")

    resp = client.post(
        f"/api/v1/projects/{project_a}/analysis/comparison",
        json={"targetProjectIds": [project_a, project_b]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    for entity in body["entities"]:
        assert entity["positivePercentage"] is None
        assert entity["averageRating"] is None
