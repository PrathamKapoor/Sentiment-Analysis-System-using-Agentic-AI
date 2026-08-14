from datetime import date

from tests.conftest_project import owner_context, create_project, create_reviews_directly

TODAY = date(2026, 6, 15)


def _seed_negative(client, project_id, headers, count=4, positive=0):
    texts = [f"Terrible experience, review {i}." for i in range(count)]
    texts += [f"Wonderful experience, review {i}." for i in range(positive)]
    create_reviews_directly(project_id, texts, review_date=TODAY)
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)


def test_create_valid_alert(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"name": "High negativity", "metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["metric"] == "negative_sentiment_percentage"
    assert body["effectiveStatus"] == "active"


def test_reject_invalid_operator(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": "~=", "threshold": 40},
        headers=headers,
    )
    assert resp.status_code == 400


def test_reject_invalid_threshold(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 150},
        headers=headers,
    )
    assert resp.status_code == 400


def test_evaluate_negative_sentiment_threshold_triggers(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative(client, project_id, headers, count=4, positive=0)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    resp = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["triggered"] is True
    assert resp.get_json()["data"]["alert"]["status"] == "open"
    assert resp.get_json()["data"]["alert"]["triggeredAt"] is not None


def test_non_triggering_rule_remains_untriggered(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative(client, project_id, headers, count=1, positive=4)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 90},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    resp = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert resp.get_json()["data"]["triggered"] is False
    assert resp.get_json()["data"]["alert"]["triggeredAt"] is None


def test_evaluate_rating_threshold(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    from app.extensions import db
    reviews = create_reviews_directly(project_id, ["Bad.", "Bad again."], review_date=TODAY)
    for r in reviews:
        r.rating = 1.5
    db.session.commit()

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "average_rating", "operator": "<", "threshold": 3},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert resp.get_json()["data"]["triggered"] is True
    assert resp.get_json()["data"]["currentValue"] == 1.5


def test_evaluate_keyword_threshold(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, [
        "Delivery delivery delivery was late.", "Delivery was fine.",
    ], review_date=TODAY)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "keyword_frequency", "operator": ">=", "threshold": 2, "keyword": "delivery"},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert resp.get_json()["data"]["triggered"] is True


def test_evaluate_aspect_negativity_threshold(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_reviews_directly(project_id, [
        "The delivery was terrible and late.", "Delivery was awful again.",
    ], review_date=TODAY)
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "aspect_negativity_percentage", "operator": ">", "threshold": 50, "aspectName": "delivery"},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert resp.get_json()["data"]["triggered"] is True


def test_repeated_evaluation_does_not_duplicate_trigger(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative(client, project_id, headers, count=4, positive=0)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    first = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    first_triggered_at = first.get_json()["data"]["alert"]["triggeredAt"]
    assert first.get_json()["data"]["changed"] is True

    second = client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)
    assert second.get_json()["data"]["changed"] is False
    assert second.get_json()["data"]["alert"]["triggeredAt"] == first_triggered_at

    from app.models import AuditLog
    triggered_logs = AuditLog.query.filter_by(action="alert.triggered", entity_id=str(alert_id)).count()
    assert triggered_logs == 1


def test_enable_disable(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    disable_resp = client.post(f"/api/v1/alerts/{alert_id}/disable", headers=headers)
    assert disable_resp.get_json()["data"]["enabled"] is False
    assert disable_resp.get_json()["data"]["effectiveStatus"] == "disabled"

    enable_resp = client.post(f"/api/v1/alerts/{alert_id}/enable", headers=headers)
    assert enable_resp.get_json()["data"]["enabled"] is True


def test_acknowledge(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_negative(client, project_id, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 10},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]
    client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)

    resp = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "open"  # no stored status change
    assert resp.get_json()["data"]["effectiveStatus"] == "acknowledged"
    assert resp.get_json()["data"]["assignedTo"]


def test_resolve_requires_notes(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    no_notes_resp = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"resolutionNotes": ""}, headers=headers)
    assert no_notes_resp.status_code == 400

    resp = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"resolutionNotes": "Fixed the issue"}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "resolved"
    assert resp.get_json()["data"]["resolutionNotes"] == "Fixed the issue"


def test_assign(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    from app.models import User
    user_id = str(User.query.first().id)
    resp = client.post(f"/api/v1/alerts/{alert_id}/assign", json={"userId": user_id}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["assignedTo"] == user_id


def test_cross_organisation_access_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/alerts/{alert_id}", headers=other_headers)
    assert resp.status_code == 404


def test_missing_permission_blocked(client):
    # Viewer holds view_reviews but not manage_alerts, per the SRS permission matrix.
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

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

    resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=viewer_headers,
    )
    assert resp.status_code == 403


def test_audit_log_created_on_create_and_evaluate(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/alerts",
        json={"metric": "negative_sentiment_percentage", "operator": ">", "threshold": 40},
        headers=headers,
    )
    alert_id = create_resp.get_json()["data"]["id"]
    client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=headers)

    from app.models import AuditLog
    actions = {a.action for a in AuditLog.query.filter_by(entity_type="alert").all()}
    assert "alert.created" in actions
    assert "alert.evaluated" in actions
