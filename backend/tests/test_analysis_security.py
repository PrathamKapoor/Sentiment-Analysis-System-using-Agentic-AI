from tests.conftest_project import owner_context, create_project, create_reviews_directly
from tests.conftest import login, auth_header


def test_invalid_uuid_filter_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/sentiment/summary",
        query_string={"sourceId": "not-a-uuid"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_uuid_in_path_returns_404_not_500(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/topics/not-a-real-uuid", headers=headers
    )
    assert resp.status_code in (400, 404)
    assert resp.status_code != 500


def test_sql_injection_like_filter_input_is_inert(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Totally normal review text."])

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/keywords",
        query_string={"search": "'; DROP TABLE reviews; --"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["items"] == []

    # Confirm the table really is still there and usable.
    still_works = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers)
    assert still_works.status_code == 200
    assert len(still_works.get_json()["data"]["items"]) == 1


def test_tenant_isolation_on_keywords_endpoint(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Secret internal product feedback."])

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/projects/{project_id}/analysis/keywords", headers=other_headers)
    assert resp.status_code == 404


def test_missing_permission_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Some review text."])

    client.post(f"/api/v1/organisations/{org_id}/users/invite", json={"email": "collector@acme.test"}, headers=headers)
    from app.models import User, OrganisationMember
    from app.extensions import db
    user = User.query.filter_by(email="collector@acme.test").first()
    user.set_password("CollectorPass123!")
    db.session.commit()
    membership = OrganisationMember.query.filter_by(organisation_id=org_id, user_id=user.id).first()
    membership.status = "active"
    db.session.commit()

    roles = client.get(f"/api/v1/organisations/{org_id}/roles", headers=headers).get_json()["data"]["items"]
    # Data Collector holds view_reviews but not manage_roles/manage_users — use a
    # role assignment scenario where the actor genuinely lacks view_reviews:
    # remove all roles is not supported, so instead verify a truly permission-less
    # custom role is blocked.
    custom_role_resp = client.post(
        f"/api/v1/organisations/{org_id}/roles",
        json={"name": "No Access", "permissionCodes": []},
        headers=headers,
    )
    no_access_role = custom_role_resp.get_json()["data"]

    client.post(
        f"/api/v1/organisations/{org_id}/roles/{no_access_role['id']}/assign",
        json={"userId": str(user.id)}, headers=headers,
    )

    no_access_login = login(client, email="collector@acme.test", password="CollectorPass123!").get_json()["data"]
    no_access_headers = {**auth_header(no_access_login["accessToken"]), "X-Organisation-Id": org_id}

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/sentiment/summary", headers=no_access_headers)
    assert resp.status_code == 403
