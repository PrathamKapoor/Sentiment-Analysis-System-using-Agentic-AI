from tests.conftest_project import owner_context, create_project, create_reviews_directly


def _seed_negative_delivery(client, project_id, headers, count=4):
    texts = [f"Delivery was terrible and late, review number {i}." for i in range(count)]
    create_reviews_directly(project_id, texts)
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)


def test_generate_recommendations_for_negative_aspect(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)

    resp = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["createdCount"] == 1
    rec = body["items"][0]
    assert rec["aspectName"] == "delivery"
    assert rec["status"] == "new"
    assert rec["priority"] in ("low", "medium", "high")
    assert "delivery" in rec["text"].lower()
    assert rec["evidence"]["aspect"] == "delivery"


def test_generate_recommendations_no_duplicate_on_rerun(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)

    client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    second = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    assert second.get_json()["data"]["createdCount"] == 0

    listed = client.get(f"/api/v1/projects/{project_id}/recommendations", headers=headers).get_json()["data"]["items"]
    assert len(listed) == 1


def test_no_recommendation_below_threshold(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, ["Delivery was excellent and fast, very happy."])
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)

    resp = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    assert resp.get_json()["data"]["createdCount"] == 0


def test_recommendation_lifecycle_assign_accept_complete(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]

    from app.models import User
    owner_user_id = str(User.query.first().id)

    assign_resp = client.post(f"/api/v1/recommendations/{rec_id}/assign", json={"userId": owner_user_id}, headers=headers)
    assert assign_resp.status_code == 200
    assert assign_resp.get_json()["data"]["status"] == "assigned"
    assert assign_resp.get_json()["data"]["assignedTo"] == owner_user_id

    accept_resp = client.post(f"/api/v1/recommendations/{rec_id}/accept", json={}, headers=headers)
    assert accept_resp.status_code == 200
    assert accept_resp.get_json()["data"]["status"] == "accepted"

    complete_resp = client.post(f"/api/v1/recommendations/{rec_id}/complete", json={}, headers=headers)
    assert complete_resp.status_code == 200
    assert complete_resp.get_json()["data"]["status"] == "completed"
    assert complete_resp.get_json()["data"]["completedAt"] is not None


def test_recommendation_reject(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]

    resp = client.post(f"/api/v1/recommendations/{rec_id}/reject", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "rejected"


def test_cannot_accept_completed_recommendation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]

    client.post(f"/api/v1/recommendations/{rec_id}/complete", json={}, headers=headers)
    resp = client.post(f"/api/v1/recommendations/{rec_id}/accept", json={}, headers=headers)
    assert resp.status_code == 409


def test_never_auto_accepted(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    assert gen.get_json()["data"]["items"][0]["status"] == "new"


def test_recommendation_filters(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/recommendations/{rec_id}/reject", json={}, headers=headers)

    resp = client.get(f"/api/v1/projects/{project_id}/recommendations", query_string={"status": "rejected"}, headers=headers)
    assert len(resp.get_json()["data"]["items"]) == 1

    resp2 = client.get(f"/api/v1/projects/{project_id}/recommendations", query_string={"status": "new"}, headers=headers)
    assert len(resp2.get_json()["data"]["items"]) == 0


def test_viewer_can_view_but_not_accept_recommendation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]

    client.post(f"/api/v1/organisations/{org_id}/users/invite", json={"email": "viewer@acme.test"}, headers=headers)
    from app.models import User, OrganisationMember
    from app.extensions import db
    user = User.query.filter_by(email="viewer@acme.test").first()
    user.set_password("ViewerPass123!")
    db.session.commit()
    membership = OrganisationMember.query.filter_by(organisation_id=org_id, user_id=user.id).first()
    membership.status = "active"
    db.session.commit()
    roles = client.get(f"/api/v1/organisations/{org_id}/roles", headers=headers).get_json()["data"]["items"]
    viewer_role = next(r for r in roles if r["name"] == "Viewer")
    client.post(f"/api/v1/organisations/{org_id}/roles/{viewer_role['id']}/assign", json={"userId": str(user.id)}, headers=headers)

    from tests.conftest import login, auth_header
    viewer_login = login(client, email="viewer@acme.test", password="ViewerPass123!").get_json()["data"]
    viewer_headers = {**auth_header(viewer_login["accessToken"]), "X-Organisation-Id": org_id}

    view_resp = client.get(f"/api/v1/recommendations/{rec_id}", headers=viewer_headers)
    assert view_resp.status_code == 200

    accept_resp = client.post(f"/api/v1/recommendations/{rec_id}/accept", json={}, headers=viewer_headers)
    assert accept_resp.status_code == 403


def test_cross_organisation_recommendation_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative_delivery(client, project_id, headers)
    gen = client.post(f"/api/v1/projects/{project_id}/recommendations/generate", json={}, headers=headers)
    rec_id = gen.get_json()["data"]["items"][0]["id"]

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/recommendations/{rec_id}", headers=other_headers)
    assert resp.status_code == 404
