from tests.conftest import register, login, auth_header


def _owner_context(client, org_name="Acme Retail", email="owner@acme.test"):
    reg = register(client, org_name=org_name, email=email).get_json()["data"]
    login_body = login(client, email=email).get_json()["data"]
    headers = {**auth_header(login_body["accessToken"]), "X-Organisation-Id": reg["organisationId"]}
    return reg["organisationId"], headers


def test_create_project(client):
    org_id, headers = _owner_context(client)
    resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["name"] == "Q3 Headphones"
    assert body["status"] == "active"


def test_project_access_by_authorised_member(client):
    org_id, headers = _owner_context(client)
    create_resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    project_id = create_resp.get_json()["data"]["id"]

    get_resp = client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.get_json()["data"]["id"] == project_id


def test_project_access_denied_across_organisations(client):
    org_id, headers = _owner_context(client)
    create_resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    project_id = create_resp.get_json()["data"]["id"]

    other_org_id, other_headers = _owner_context(
        client, org_name="Other Org", email="other@other.test"
    )
    resp = client.get(f"/api/v1/projects/{project_id}", headers=other_headers)
    assert resp.status_code == 404


def test_project_archive(client):
    org_id, headers = _owner_context(client)
    create_resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    project_id = create_resp.get_json()["data"]["id"]

    archive_resp = client.post(
        f"/api/v1/projects/{project_id}/archive", json={"archived": True}, headers=headers
    )
    assert archive_resp.status_code == 200
    assert archive_resp.get_json()["data"]["status"] == "archived"

    unarchive_resp = client.post(
        f"/api/v1/projects/{project_id}/archive", json={"archived": False}, headers=headers
    )
    assert unarchive_resp.get_json()["data"]["status"] == "active"


def test_duplicate_project_name_rejected(client):
    org_id, headers = _owner_context(client)
    client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    dup_resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    assert dup_resp.status_code == 409


def test_duplicate_project_membership_prevented(client):
    org_id, headers = _owner_context(client)
    create_resp = client.post("/api/v1/projects", json={"name": "Q3 Headphones"}, headers=headers)
    project_id = create_resp.get_json()["data"]["id"]

    from app.models import User
    user = User.query.filter_by(email="owner@acme.test").first()

    dup_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"userId": str(user.id)},
        headers=headers,
    )
    assert dup_resp.status_code == 409
    assert dup_resp.get_json()["error"]["code"] == "CONFLICT"


def test_duplicate_organisation_membership_prevented(client):
    org_id, headers = _owner_context(client)
    from app.models import User
    from app.errors.exceptions import ConflictError
    from app.services.organisation_service import invite_member

    user = User.query.filter_by(email="owner@acme.test").first()
    try:
        invite_member(org_id, "owner@acme.test")
        raised = False
    except ConflictError:
        raised = True
    assert raised is True
