from datetime import date

from tests.conftest_project import owner_context, create_project, create_reviews_directly
from tests.conftest import login, auth_header

TODAY = date(2026, 6, 15)


def _seed_and_analyse(client, project_id, headers):
    create_reviews_directly(project_id, [
        "Delivery was terrible and late.", "Great product quality overall.",
    ], review_date=TODAY)
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)


def test_generate_summary_uses_correct_stored_analytics(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["approvalStatus"] == "draft"
    assert body["isAiGenerated"] is True

    summary_data = client.get(
        f"/api/v1/projects/{project_id}/analysis/sentiment/summary", headers=headers
    ).get_json()["data"]
    assert f"{summary_data['analysedReviews']} analysed reviews" in body["sections"]["sentiment"]
    assert f"{summary_data['positive']['percentage']}%" in body["sections"]["sentiment"]


def test_summary_missing_analytics_handled(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-01-01", "dateTo": "2026-01-31"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert "No analysed reviews" in resp.get_json()["data"]["sections"]["sentiment"]


def test_invalid_date_range_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-30", "dateTo": "2026-06-01"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_submit_approve_workflow(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]

    submit_resp = client.post(f"/api/v1/ai-summaries/{summary_id}/submit-for-review", headers=headers)
    assert submit_resp.status_code == 200
    assert submit_resp.get_json()["data"]["approvalStatus"] == "draft"  # no stored pending state

    approve_resp = client.post(f"/api/v1/ai-summaries/{summary_id}/approve", json={}, headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.get_json()["data"]["approvalStatus"] == "approved"
    assert approve_resp.get_json()["data"]["approvedBy"]


def test_reject_summary(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]

    resp = client.post(f"/api/v1/ai-summaries/{summary_id}/reject", json={"reason": "not accurate"}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["approvalStatus"] == "rejected"


def test_unauthorised_approval_denied(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]

    client.post(f"/api/v1/organisations/{org_id}/users/invite", json={"email": "analyst@acme.test"}, headers=headers)
    from app.models import User, OrganisationMember
    from app.extensions import db
    user = User.query.filter_by(email="analyst@acme.test").first()
    user.set_password("AnalystPass123!")
    db.session.commit()
    membership = OrganisationMember.query.filter_by(organisation_id=org_id, user_id=user.id).first()
    membership.status = "active"
    db.session.commit()
    roles = client.get(f"/api/v1/organisations/{org_id}/roles", headers=headers).get_json()["data"]["items"]
    analyst_role = next(r for r in roles if r["name"] == "Analyst")
    client.post(f"/api/v1/organisations/{org_id}/roles/{analyst_role['id']}/assign", json={"userId": str(user.id)}, headers=headers)

    analyst_login = login(client, email="analyst@acme.test", password="AnalystPass123!").get_json()["data"]
    analyst_headers = {**auth_header(analyst_login["accessToken"]), "X-Organisation-Id": org_id}

    resp = client.post(f"/api/v1/ai-summaries/{summary_id}/approve", json={}, headers=analyst_headers)
    assert resp.status_code == 403  # Analyst lacks approve_ai_output


def test_viewer_read_only(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]

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

    viewer_login = login(client, email="viewer@acme.test", password="ViewerPass123!").get_json()["data"]
    viewer_headers = {**auth_header(viewer_login["accessToken"]), "X-Organisation-Id": org_id}

    view_resp = client.get(f"/api/v1/ai-summaries/{summary_id}", headers=viewer_headers)
    assert view_resp.status_code == 200

    approve_resp = client.post(f"/api/v1/ai-summaries/{summary_id}/approve", json={}, headers=viewer_headers)
    assert approve_resp.status_code == 403


def test_cross_organisation_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/ai-summaries/{summary_id}", headers=other_headers)
    assert resp.status_code == 404


def test_audit_logs_created(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    summary_id = gen.get_json()["data"]["id"]
    client.post(f"/api/v1/ai-summaries/{summary_id}/approve", json={}, headers=headers)

    from app.models import AuditLog
    actions = {a.action for a in AuditLog.query.filter_by(entity_type="ai_summary").all()}
    assert "ai_summary.generated" in actions
    assert "ai_summary.approved" in actions


def test_no_fabricated_metric_in_deterministic_generator(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    summary_resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/sentiment/summary", headers=headers
    ).get_json()["data"]
    gen = client.post(
        f"/api/v1/projects/{project_id}/ai-summaries",
        json={"summaryType": "overall", "dateFrom": "2026-06-01", "dateTo": "2026-06-30"},
        headers=headers,
    )
    text = gen.get_json()["data"]["sections"]["sentiment"]
    # Every number quoted in the summary must equal a number already returned
    # by the underlying (already-tested) analytics endpoint — not invented.
    assert str(summary_resp["analysedReviews"]) in text
    assert f"{summary_resp['positive']['percentage']}%" in text
    assert f"{summary_resp['negative']['percentage']}%" in text
