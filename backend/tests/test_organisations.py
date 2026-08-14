from tests.conftest import register, login, auth_header


def test_get_organisation(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    resp = client.get(
        f"/api/v1/organisations/{reg['organisationId']}",
        headers=auth_header(login_body["accessToken"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["name"] == "Acme Retail"


def test_update_organisation_as_owner(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    resp = client.patch(
        f"/api/v1/organisations/{reg['organisationId']}",
        json={"name": "Acme Retail Renamed"},
        headers=auth_header(login_body["accessToken"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["name"] == "Acme Retail Renamed"


def test_invite_member_then_prevent_duplicate(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    org_id = reg["organisationId"]
    headers = auth_header(login_body["accessToken"])

    invite_resp = client.post(
        f"/api/v1/organisations/{org_id}/users/invite",
        json={"email": "analyst@acme.test"},
        headers=headers,
    )
    assert invite_resp.status_code == 201

    duplicate_resp = client.post(
        f"/api/v1/organisations/{org_id}/users/invite",
        json={"email": "analyst@acme.test"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 409
    assert duplicate_resp.get_json()["error"]["code"] == "CONFLICT"


def test_organisation_endpoint_without_membership_not_found(client):
    reg = register(client).get_json()["data"]
    # A second, unrelated org + user should not be able to see the first org.
    register(client, org_name="Other Org", email="other@other.test", name="Other Owner")
    other_login = login(client, email="other@other.test").get_json()["data"]

    resp = client.get(
        f"/api/v1/organisations/{reg['organisationId']}",
        headers=auth_header(other_login["accessToken"]),
    )
    assert resp.status_code == 404
