import io

from tests.conftest_project import owner_context, create_project

CSV_CONTENT = "text,rating\n<b>Nice</b>   product   here,4\n"


def _process_one_review(client, project_id, headers):
    data = {"file": (io.BytesIO(CSV_CONTENT.encode("utf-8")), "r.csv"), "fileType": "csv"}
    dataset_id = client.post(
        f"/api/v1/projects/{project_id}/datasets", data=data, headers=headers,
        content_type="multipart/form-data",
    ).get_json()["data"]["datasetId"]
    client.post(f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text", "rating": "rating"}, headers=headers)
    client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers)
    client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers)
    reviews = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers).get_json()["data"]["items"]
    return reviews[0]


def test_text_cleaning_strips_html_and_collapses_whitespace(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)
    assert review["text"] == "Nice product here"


def test_get_review_detail(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    resp = client.get(f"/api/v1/reviews/{review['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["id"] == review["id"]


def test_update_review_text(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    resp = client.patch(
        f"/api/v1/reviews/{review['id']}", json={"text": "Corrected text"}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["text"] == "Corrected text"


def test_mark_review_as_spam(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    resp = client.post(f"/api/v1/reviews/{review['id']}/mark-spam", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["isSpam"] is True


def test_remove_duplicate_flag_via_patch(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    resp = client.patch(
        f"/api/v1/reviews/{review['id']}", json={"isDuplicate": True}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["isDuplicate"] is True


def test_review_access_denied_across_organisations(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/reviews/{review['id']}", headers=other_headers)
    assert resp.status_code == 404


def test_permission_denied_for_viewer_marking_spam(client):
    # Viewer holds view_reviews (can list/read) but not correct_sentiment
    # (can't edit/moderate) — per the SRS permission matrix.
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    review = _process_one_review(client, project_id, headers)

    client.post(
        f"/api/v1/organisations/{org_id}/users/invite",
        json={"email": "viewer@acme.test"}, headers=headers,
    )
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
    client.post(
        f"/api/v1/organisations/{org_id}/roles/{viewer_role['id']}/assign",
        json={"userId": str(user.id)}, headers=headers,
    )

    from tests.conftest import login, auth_header
    viewer_login = login(client, email="viewer@acme.test", password="ViewerPass123!").get_json()["data"]
    viewer_headers = {**auth_header(viewer_login["accessToken"]), "X-Organisation-Id": org_id}

    list_resp = client.get(f"/api/v1/projects/{project_id}/reviews", headers=viewer_headers)
    assert list_resp.status_code == 200  # Viewer CAN view

    spam_resp = client.post(f"/api/v1/reviews/{review['id']}/mark-spam", json={}, headers=viewer_headers)
    assert spam_resp.status_code == 403  # Viewer CANNOT moderate
