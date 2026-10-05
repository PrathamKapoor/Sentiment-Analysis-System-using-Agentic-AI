from app.services.security_intelligence_service import extract_security_signals
from tests.test_product_entity_intelligence import _create_project, _owner_context


def test_specific_account_compromise_phrase_creates_evidence_spans():
    text = "My account was taken over after someone logged in without permission."
    findings = extract_security_signals(text)
    assert len(findings) == 1
    assert findings[0]["findingType"] == "ACCOUNT_COMPROMISE"
    assert findings[0]["status"] == "needs_review"
    assert findings[0]["confidence"] is None
    assert text[slice(*findings[0]["evidence"][0]["sourceSpan"])].lower() == "account was taken over"


def test_generic_security_word_does_not_become_a_security_incident():
    assert extract_security_signals("The new security page looks polished.") == []


def test_privacy_signal_is_classified_separately_from_account_compromise():
    findings = extract_security_signals("The app exposed my personal data to other users.")
    assert [finding["findingType"] for finding in findings] == ["PERSONAL_DATA_EXPOSURE"]


def _seed_security_review(client, app, headers):
    from app.extensions import db
    from app.models import Dataset, Review, User

    project_id = _create_project(client, headers, name="Security Project")
    user = User.query.filter_by(email="entity-owner@example.test").first()
    dataset = Dataset(project_id=project_id, file_type="csv", file_path="unused.csv",
                      status="processed", uploaded_by=user.id)
    db.session.add(dataset)
    db.session.flush()
    db.session.add(Review(project_id=project_id, dataset_id=dataset.id,
                          text="My account was taken over after a strange login."))
    db.session.commit()
    return project_id


def test_security_findings_are_scoped_and_require_human_triage(client, app):
    headers = _owner_context(client, email="entity-owner@example.test")
    project_id = _seed_security_review(client, app, headers)

    analyzed = client.post(
        f"/api/v1/projects/{project_id}/security-findings/analyze", headers=headers,
    )
    assert analyzed.status_code == 200
    assert analyzed.get_json()["data"]["created"] == 1
    listing = client.get(f"/api/v1/projects/{project_id}/security-findings", headers=headers)
    finding = listing.get_json()["data"]["items"][0]
    assert finding["status"] == "needs_review"
    assert finding["evidence"]

    other = _owner_context(client, org_name="Unrelated", email="other-security@example.test")
    assert client.get(
        f"/api/v1/projects/{project_id}/security-findings", headers=other,
    ).status_code == 404
    assert client.patch(
        f"/api/v1/projects/{project_id}/security-findings/{finding['id']}",
        json={"status": "confirmed"}, headers=other,
    ).status_code == 404

    invalid = client.patch(
        f"/api/v1/projects/{project_id}/security-findings/{finding['id']}",
        json={"status": "resolved"}, headers=headers,
    )
    assert invalid.status_code == 400
    confirmed = client.patch(
        f"/api/v1/projects/{project_id}/security-findings/{finding['id']}",
        json={"status": "confirmed", "analystNotes": "Reviewed against the source review."},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.get_json()["data"]["status"] == "confirmed"


def test_reanalysis_marks_changed_evidence_stale_and_reopens_changed_match(client, app):
    from app.extensions import db
    from app.models import Review

    headers = _owner_context(client, email="entity-owner@example.test")
    project_id = _seed_security_review(client, app, headers)
    endpoint = f"/api/v1/projects/{project_id}/security-findings"
    assert client.post(f"{endpoint}/analyze", headers=headers).status_code == 200
    finding = client.get(endpoint, headers=headers).get_json()["data"]["items"][0]
    assert finding["status"] == "needs_review"
    assert client.patch(
        f"{endpoint}/{finding['id']}",
        json={"status": "confirmed", "analystNotes": "Checked original wording."},
        headers=headers,
    ).status_code == 200

    with app.app_context():
        review = Review.query.filter_by(project_id=project_id).first()
        review.text = review.text + " I added surrounding context without changing the matched phrase."
        db.session.commit()
    assert client.post(f"{endpoint}/analyze", headers=headers).status_code == 200
    same_phrase = client.get(endpoint, headers=headers).get_json()["data"]["items"][0]
    assert same_phrase["status"] == "needs_review"
    assert same_phrase["analystNotes"] is None
    assert same_phrase["reviewedBy"] is None

    with app.app_context():
        review = Review.query.filter_by(project_id=project_id).first()
        review.text = "My account is working well now."
        db.session.commit()
    stale = client.post(f"{endpoint}/analyze", headers=headers)
    assert stale.status_code == 200
    result = stale.get_json()["data"]
    assert result["stale"] == 1
    stale_finding = client.get(endpoint, headers=headers).get_json()["data"]["items"][0]
    assert stale_finding["status"] == "stale"
    assert client.patch(
        f"{endpoint}/{finding['id']}", json={"status": "confirmed"}, headers=headers,
    ).status_code == 409

    with app.app_context():
        review = Review.query.filter_by(project_id=project_id).first()
        review.text = "I noticed an unauthorized login after a password reset."
        db.session.commit()
    refreshed = client.post(f"{endpoint}/analyze", headers=headers)
    assert refreshed.status_code == 200
    current = client.get(endpoint, headers=headers).get_json()["data"]["items"][0]
    assert current["status"] == "needs_review"
    assert current["evidence"][0]["text"].lower() == "unauthorized login"
    assert current["analystNotes"] is None
    assert current["reviewedBy"] is None
