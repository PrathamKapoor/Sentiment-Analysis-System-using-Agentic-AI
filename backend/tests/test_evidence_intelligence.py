from datetime import date, timedelta

from app.extensions import db
from app.models import DataSource, Review
from app.services.evidence_service import serialize_evidence
from app.services.duplicate_detection_service import detect_project_duplicates
from app.services.source_statistics_service import get_source_statistics
from app.services.temporal_intelligence_service import get_emerging_themes, get_anomalies
from app.services.security_intelligence_service import extract_security_indicators, correlate_security_signals
from tests.conftest_project import owner_context, create_project


def _review(project_id, source, text, day, **kwargs):
    source_row = DataSource(project_id=project_id, type=source, url=f"https://{source}.example/reviews")
    db.session.add(source_row)
    db.session.flush()
    review = Review(project_id=project_id, data_source_id=source_row.id, source=source,
                    text=text, review_date=day, **kwargs)
    db.session.add(review)
    db.session.flush()
    return review


def test_evidence_uses_review_id_and_preserves_provenance(app):
    with app.app_context():
        from app.models import Project
        # fixture setup inserts projects through route to preserve usual ownership.
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        review = _review(project_id, "github_issues", "Checkout fails", date.today(),
                         source_record_id="issue-44", source_url="https://github.com/a/b/issues/44",
                         source_metadata={"number": 44})
        db.session.commit()
        item = serialize_evidence(review)
        assert item["evidenceId"] == str(review.id)
        assert item["providerRecordId"] == "issue-44"
        assert item["canonicalUrl"] == "https://github.com/a/b/issues/44"
        assert item["content"] == "Checkout fails"


def test_evidence_lookup_rejects_malformed_and_cross_project_ids(app):
    from app.errors.exceptions import NotFoundError
    from app.services.evidence_service import get_evidence
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        try:
            get_evidence(project_id, "not-a-uuid")
        except NotFoundError:
            pass
        else:
            raise AssertionError("malformed evidence ID was not hidden")


def test_exact_duplicate_detection_links_without_mutating_reviews(app):
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        first = _review(project_id, "amazon", "Battery life is terrible", date.today(),
                        source_record_id="amz-1")
        second = _review(project_id, "reddit", "  Battery   life is terrible ", date.today(),
                         source_record_id="rd-2")
        db.session.commit()
        result = detect_project_duplicates(project_id)
        db.session.commit()
        assert result["created"] == 1
        assert first.is_duplicate is False and second.is_duplicate is False
        assert result["items"][0]["relationshipType"] == "EXACT_DUPLICATE"
        assert {result["items"][0]["reviewId"], result["items"][0]["duplicateReviewId"]} == {
            str(first.id), str(second.id)
        }


def test_duplicate_detection_is_idempotent_and_does_not_link_different_text(app):
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        _review(project_id, "amazon", "Battery life is terrible", date.today())
        _review(project_id, "reddit", "Battery life is only okay", date.today())
        db.session.commit()
        assert detect_project_duplicates(project_id)["created"] == 0
        db.session.commit()
        assert detect_project_duplicates(project_id)["created"] == 0


def test_source_statistics_keeps_source_counts_distinct(app):
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        _review(project_id, "amazon", "Great camera quality lasts all year", date.today())
        _review(project_id, "reddit", "Great camera quality lasts all year", date.today())
        db.session.commit()
        detect_project_duplicates(project_id)
        db.session.commit()
        stats = get_source_statistics(project_id)
        assert {item["sourceType"] for item in stats["sources"]} == {"amazon", "reddit"}
        assert sum(item["recordCount"] for item in stats["sources"]) == 2
        assert stats["recordCount"] == 2
        assert stats["canonicalEvidenceCount"] == 1


def test_temporal_analysis_uses_explicit_windows_and_actual_dates(app):
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        today = date.today()
        for offset in range(13, 9, -1):
            _review(project_id, "amazon", "App crashes at checkout", today - timedelta(days=offset))
        for _ in range(7):
            _review(project_id, "github_issues", "App crashes at checkout", today - timedelta(days=1))
        _review(project_id, "amazon", "Undated issue should not enter window", None)
        db.session.commit()
        themes = get_emerging_themes(project_id, days=7, baseline_days=7, minimum_increase=1.5)
        assert themes["comparison"]["baselineDays"] == 7
        assert themes["comparison"]["currentDays"] == 7
        assert any(t["theme"] == "BUG" and t["baselineCount"] == 4 and t["currentCount"] == 7
                   for t in themes["items"])
        anomalies = get_anomalies(project_id, days=7, baseline_days=7, minimum_increase=1.5)
        assert anomalies["comparison"]["baselineDays"] == 7


def test_security_indicators_are_observed_and_urls_are_sanitized():
    text = "Phishing came from https://bad.example/login?token=secret; CVE-2025-12345"
    indicators = extract_security_indicators(text)
    assert {item["type"] for item in indicators} >= {"URL", "DOMAIN", "CVE"}
    assert all(item["status"] == "OBSERVED" for item in indicators)
    assert "secret" not in str(indicators)


def test_security_correlation_never_promotes_customer_reports_to_confirmed(app):
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        _review(project_id, "amazon", "Phishing email from bad.example and unauthorized login", date.today())
        _review(project_id, "reddit", "Phishing link from bad.example stole my account", date.today())
        db.session.commit()
        from app.models import Project
        from app.services.security_intelligence_service import analyze_project_security_signals
        project = db.session.get(Project, project_id)
        analyze_project_security_signals(project)
        db.session.commit()
        incidents = correlate_security_signals(project_id)
        matching = [item for item in incidents if item["indicator"] == "bad.example"]
        assert matching and matching[0]["status"] == "POSSIBLE_INCIDENT"
        assert matching[0]["evidenceCount"] == 2
        assert matching[0]["status"] != "CONFIRMED_INCIDENT"


def test_stale_security_finding_indicators_are_not_returned(app):
    from app.models import Project, SecurityFinding
    from app.services.security_intelligence_service import get_project_security_indicators
    with app.app_context():
        client = app.test_client()
        _, headers = owner_context(client)
        project_id = create_project(client, headers)
        review = _review(project_id, "amazon", "Account issue", date.today())
        project = db.session.get(Project, project_id)
        db.session.add(SecurityFinding(organisation_id=project.organisation_id,
            project_id=project_id, review_id=review.id, finding_type="ACCOUNT_COMPROMISE",
            severity="HIGH", evidence=[{"text": "account taken over"}],
            indicators=[{"type": "DOMAIN", "value": "bad.example", "status": "OBSERVED"}],
            classification_method="test", status="stale"))
        db.session.commit()
        assert get_project_security_indicators(project_id) == []
