from tests.conftest_project import owner_context, create_project, create_reviews_directly


def test_default_aspects_still_work_without_vocab(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["The battery is terrible."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    assert any(i["name"] == "battery" for i in items)


def test_create_vocab_item_and_aspect_uses_it(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers, name="Restaurant Project")
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "food", "surfaceForms": ["food", "meal", "dish"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    create_reviews_directly(project_id, ["The food was cold but the meal was delicious."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    names = {i["name"] for i in items}
    assert "food" in names


def test_synonyms_work_for_custom_aspect(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "waiting time", "surfaceForms": ["waiting time", "wait", "queue", "waiting"]},
        headers=headers,
    )
    create_reviews_directly(project_id, ["The queue was far too long, we waited for hours."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    assert any(i["name"] == "waiting time" for i in items)


def test_fallback_global_aspects_still_apply_alongside_custom(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "ambience", "surfaceForms": ["ambience", "atmosphere"]},
        headers=headers,
    )
    # This review mentions both a global aspect (battery) and a custom one (ambience)
    create_reviews_directly(project_id, ["The battery is weak but the ambience is lovely."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    names = {i["name"] for i in items}
    assert "battery" in names
    assert "ambience" in names


def test_vocab_crud_list_update_delete(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    created = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "cleanliness", "surfaceForms": ["cleanliness", "clean", "hygiene"]},
        headers=headers,
    ).get_json()["data"]
    vocab_id = created["id"]
    # patch isActive
    patch = client.patch(
        f"/api/v1/projects/{project_id}/aspect-vocabulary/{vocab_id}",
        json={"isActive": False}, headers=headers,
    )
    assert patch.status_code == 200
    assert patch.get_json()["data"]["isActive"] is False
    # delete
    delete = client.delete(f"/api/v1/projects/{project_id}/aspect-vocabulary/{vocab_id}", headers=headers)
    assert delete.status_code == 200
    listed = client.get(f"/api/v1/projects/{project_id}/aspect-vocabulary", headers=headers).get_json()["data"]["items"]
    assert not any(i["id"] == vocab_id for i in listed)


def test_vocab_cross_tenant_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/projects/{project_id}/aspect-vocabulary", headers=other_headers)
    assert resp.status_code == 404
    create = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "food", "surfaceForms": ["food"]},
        headers=other_headers,
    )
    assert create.status_code == 404


def test_vocab_duplicate_canonical_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "food", "surfaceForms": ["food"]},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "food", "surfaceForms": ["food"]},
        headers=headers,
    )
    assert second.status_code in (400, 409)


def test_vocab_requires_auth(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.get(f"/api/v1/projects/{project_id}/aspect-vocabulary")
    assert resp.status_code in (401, 403, 404)


def test_vocab_invalid_payload_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "", "surfaceForms": []},
        headers=headers,
    )
    assert resp.status_code == 400


def test_deactivated_custom_aspect_not_detected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    created = client.post(
        f"/api/v1/projects/{project_id}/aspect-vocabulary",
        json={"canonicalName": "waiting time", "surfaceForms": ["queue", "waiting time"]},
        headers=headers,
    ).get_json()["data"]
    client.patch(
        f"/api/v1/projects/{project_id}/aspect-vocabulary/{created['id']}",
        json={"isActive": False}, headers=headers,
    )
    create_reviews_directly(project_id, ["The queue was far too long."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)
    items = client.get(f"/api/v1/projects/{project_id}/analysis/aspects", headers=headers).get_json()["data"]["items"]
    # Deactivated vocabulary must not be detected
    assert not any(i["name"] == "waiting time" for i in items)
