from tests.conftest import register, login, auth_header


def test_register_creates_user_org_and_owner_membership(client):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["success"] is True
    assert "organisationId" in body["data"]
    assert "userId" in body["data"]
    assert "accessToken" in body["data"]
    assert "refreshToken" in body["data"]


def test_register_assigns_owner_role(client):
    register(client)
    login_resp = login(client)
    body = login_resp.get_json()["data"]
    assert "Organisation Owner" in body["roles"]
    assert "manage_users" in body["permissions"]
    assert "create_project" in body["permissions"]


def test_register_duplicate_email_rejected(client):
    register(client)
    resp = register(client, org_name="Another Org")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"


def test_login_success(client):
    register(client)
    resp = login(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "owner@acme.test"
    assert body["data"]["activeOrganisation"] is not None


def test_login_failure_wrong_password(client):
    register(client)
    resp = login(client, password="WrongPassword123")
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_failure_unknown_email(client):
    resp = login(client, email="nobody@nowhere.test")
    assert resp.status_code == 401


def test_refresh_token_issues_new_pair(client):
    register(client)
    login_body = login(client).get_json()["data"]
    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        headers=auth_header(login_body["refreshToken"]),
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.get_json()["data"]
    assert new_tokens["accessToken"] != login_body["accessToken"]
    assert new_tokens["refreshToken"] != login_body["refreshToken"]


def test_refresh_token_is_single_use(client):
    register(client)
    login_body = login(client).get_json()["data"]
    first = client.post("/api/v1/auth/refresh", headers=auth_header(login_body["refreshToken"]))
    assert first.status_code == 200
    second = client.post("/api/v1/auth/refresh", headers=auth_header(login_body["refreshToken"]))
    assert second.status_code == 401


def test_protected_endpoint_without_token_rejected(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    register(client)
    login_body = login(client).get_json()["data"]
    resp = client.get("/api/v1/auth/me", headers=auth_header(login_body["accessToken"]))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["user"]["email"] == "owner@acme.test"
    assert data["activeOrganisation"] is not None
    assert "Organisation Owner" in data["roles"]
    assert "upload_dataset" in data["permissions"]
    assert "manage_data_sources" in data["permissions"]


def test_logout_revokes_token(client):
    register(client)
    login_body = login(client).get_json()["data"]
    logout_resp = client.post("/api/v1/auth/logout", headers=auth_header(login_body["accessToken"]))
    assert logout_resp.status_code == 200
    reuse_resp = client.get("/api/v1/auth/me", headers=auth_header(login_body["accessToken"]))
    assert reuse_resp.status_code == 401
