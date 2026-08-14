from tests.conftest import register, login, auth_header


def _setup_org_with_analyst(client):
    reg = register(client).get_json()["data"]
    owner_login = login(client).get_json()["data"]
    org_id = reg["organisationId"]
    owner_headers = auth_header(owner_login["accessToken"])

    client.post(
        f"/api/v1/organisations/{org_id}/users/invite",
        json={"email": "analyst@acme.test"},
        headers=owner_headers,
    )
    # Phase 1 shortcut: give the invited placeholder user a real password directly
    # via the DB so we can log them in without an email-based acceptance flow.
    from app.models import User
    from app.extensions import db
    user = User.query.filter_by(email="analyst@acme.test").first()
    user.set_password("AnalystPass123!")
    user.notification_prefs = user.notification_prefs or {}
    db.session.commit()

    from app.models import OrganisationMember
    membership = OrganisationMember.query.filter_by(
        organisation_id=org_id, user_id=user.id
    ).first()
    membership.status = "active"
    db.session.commit()

    return org_id, owner_headers, user


def test_list_roles_includes_built_ins(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    resp = client.get(
        f"/api/v1/organisations/{reg['organisationId']}/roles",
        headers=auth_header(login_body["accessToken"]),
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.get_json()["data"]["items"]]
    assert "Organisation Owner" in names
    assert "Analyst" in names


def test_create_custom_role(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    resp = client.post(
        f"/api/v1/organisations/{reg['organisationId']}/roles",
        json={"name": "QA Reviewer", "permissionCodes": ["view_reviews", "correct_sentiment"]},
        headers=auth_header(login_body["accessToken"]),
    )
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["name"] == "QA Reviewer"
    assert set(body["permissions"]) == {"view_reviews", "correct_sentiment"}


def test_assign_role_to_member(client):
    org_id, owner_headers, analyst_user = _setup_org_with_analyst(client)

    roles_resp = client.get(f"/api/v1/organisations/{org_id}/roles", headers=owner_headers)
    analyst_role = next(r for r in roles_resp.get_json()["data"]["items"] if r["name"] == "Analyst")

    assign_resp = client.post(
        f"/api/v1/organisations/{org_id}/roles/{analyst_role['id']}/assign",
        json={"userId": str(analyst_user.id)},
        headers=owner_headers,
    )
    assert assign_resp.status_code == 200
    assert "Analyst" in assign_resp.get_json()["data"]["roles"]


def test_permission_denied_for_member_without_permission(client):
    org_id, owner_headers, analyst_user = _setup_org_with_analyst(client)

    roles_resp = client.get(f"/api/v1/organisations/{org_id}/roles", headers=owner_headers)
    analyst_role = next(r for r in roles_resp.get_json()["data"]["items"] if r["name"] == "Analyst")
    client.post(
        f"/api/v1/organisations/{org_id}/roles/{analyst_role['id']}/assign",
        json={"userId": str(analyst_user.id)},
        headers=owner_headers,
    )

    analyst_login = login(client, email="analyst@acme.test", password="AnalystPass123!").get_json()["data"]
    analyst_headers = auth_header(analyst_login["accessToken"])

    # Analyst has view_reviews/upload_dataset/etc. but not create_project.
    resp = client.post(
        "/api/v1/projects",
        json={"name": "Should Fail"},
        headers={**analyst_headers, "X-Organisation-Id": org_id},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"


def test_owner_role_cannot_be_deleted(client):
    reg = register(client).get_json()["data"]
    login_body = login(client).get_json()["data"]
    headers = auth_header(login_body["accessToken"])
    roles_resp = client.get(f"/api/v1/organisations/{reg['organisationId']}/roles", headers=headers)
    owner_role = next(r for r in roles_resp.get_json()["data"]["items"] if r["name"] == "Organisation Owner")

    resp = client.delete(
        f"/api/v1/organisations/{reg['organisationId']}/roles/{owner_role['id']}",
        headers=headers,
    )
    assert resp.status_code == 400
