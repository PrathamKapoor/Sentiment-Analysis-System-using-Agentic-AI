from tests.conftest_project import owner_context, create_project


def test_create_and_list_source(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "https://reviews.example.com", "keywords": ["headphones"]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["enabled"] is True

    list_resp = client.get(f"/api/v1/projects/{project_id}/sources", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.get_json()["data"]["items"]) == 1


def test_invalid_url_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "not-a-url"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_disable_source(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "forum", "url": "https://forum.example.com"},
        headers=headers,
    )
    source_id = create_resp.get_json()["data"]["id"]

    patch_resp = client.patch(
        f"/api/v1/sources/{source_id}", json={"enabled": False}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["data"]["enabled"] is False


def test_source_from_other_org_not_found(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "forum", "url": "https://forum.example.com"},
        headers=headers,
    )
    source_id = create_resp.get_json()["data"]["id"]

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.patch(f"/api/v1/sources/{source_id}", json={"enabled": False}, headers=other_headers)
    assert resp.status_code == 404


def test_delete_source(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "forum", "url": "https://forum.example.com"},
        headers=headers,
    )
    source_id = create_resp.get_json()["data"]["id"]
    del_resp = client.delete(f"/api/v1/sources/{source_id}", headers=headers)
    assert del_resp.status_code == 200

    list_resp = client.get(f"/api/v1/projects/{project_id}/sources", headers=headers)
    assert list_resp.get_json()["data"]["items"] == []
