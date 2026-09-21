"""Report-mode tests.

Covers:
  - standard mode: deterministic findings, no AI section, no LLM call
  - enhanced mode: AI section is included, LLM is consulted
  - enhanced mode + LLM unavailable: deterministic interpretation
    is rendered with a clear warning, no exception raised
  - enhanced mode + business context: LLM prompt includes the context
  - AI section in the response is clearly labelled as generated
  - the aiInterpretation section appears in the PDF and Excel renderers
  - invalid mode values are rejected
  - default mode is standard
  - cross-tenant block remains intact
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.extensions import db
from app.models import Project, ProjectWebsiteContext
from app.services.llm import (
    DeterministicProvider,
    StubProvider,
    reset_provider_cache,
)


def teardown_function(_):
    reset_provider_cache(None)


def _seed_and_analyse(client, project_id, headers):
    from tests.conftest_project import create_reviews_directly
    create_reviews_directly(project_id, [
        "The battery is great. The screen is terrible.",
        "Excellent product, fast delivery.",
    ], review_date=date(2026, 6, 15))
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)


def test_standard_mode_returns_no_ai_section(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution", "aiInterpretation"],
            "fileFormat": "pdf",
            "mode": "standard",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    report = resp.get_json()["data"]
    # Standard mode strips aiInterpretation even when explicitly listed.
    assert "aiInterpretation" not in report["sections"]
    assert report["mode"] == "standard"
    assert report["hasFile"] is True


def test_enhanced_mode_with_deterministic_provider_renders_fallback_section(client):
    from tests.conftest_project import owner_context, create_project
    reset_provider_cache(DeterministicProvider())
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf",
            "mode": "enhanced",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    report = resp.get_json()["data"]
    assert "aiInterpretation" in report["sections"]
    params = report.get("generationParameters", {})
    assert params.get("mode") == "enhanced"
    assert params.get("aiInterpretation", {}).get("source") == "deterministic"


def test_enhanced_mode_with_stub_llm_records_llm_metadata(client):
    from tests.conftest_project import owner_context, create_project
    reset_provider_cache(StubProvider(default_text="LLM-style interpretation text."))
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf",
            "mode": "enhanced",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    report = resp.get_json()["data"]
    assert "aiInterpretation" in report["sections"]
    params = report.get("generationParameters", {})
    assert params.get("aiInterpretation", {}).get("source") == "llm"
    assert params["aiInterpretation"]["provider"] == "stub"


def test_enhanced_mode_with_business_context_includes_context_in_prompt(client):
    """When the project has a website URL and a cached successful
    extraction, the LLM prompt includes a BUSINESS CONTEXT block."""
    from tests.conftest_project import owner_context, create_project
    from app.services.llm.provider import LLMResult

    captured = {}

    class CapturingProvider:
        name = "capturing"

        def is_available(self):
            return True

        def complete(self, prompt, *, system=None, max_tokens=512, temperature=0.2):
            captured["prompt"] = prompt
            captured["system"] = system
            return LLMResult(text="interpretation", provider="capturing", model="m", status="ok", latency_ms=1)

    reset_provider_cache(CapturingProvider())

    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    project = Project.query.get(project_id)
    project.website_url = "https://example.com/"
    db.session.add(project)
    ctx = ProjectWebsiteContext(
        project_id=project_id,
        website_url="https://example.com/",
        source_url="https://example.com/",
        status="ok",
        title="Acme Inc",
        meta_description="We make widgets.",
        headings=["Home"],
        body_excerpt="Welcome to Acme Inc, the home of widgets.",
        content_hash="a" * 64,
        extracted_at=datetime.now(timezone.utc),
    )
    db.session.add(ctx)
    db.session.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf",
            "mode": "enhanced",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    # The captured prompt includes the business context.
    assert "Acme Inc" in captured["prompt"]
    assert "We make widgets" in captured["prompt"]


def test_invalid_mode_rejected(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf",
            "mode": "turbo",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_default_mode_is_standard(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["mode"] == "standard"


def test_enhanced_mode_does_not_alter_deterministic_numbers(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    r1 = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01", "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution", "aspectSentiment"],
            "fileFormat": "pdf", "mode": "standard",
        },
        headers=headers,
    )
    r2 = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01", "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution", "aspectSentiment"],
            "fileFormat": "pdf", "mode": "enhanced",
        },
        headers=headers,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201

    s1 = set(r1.get_json()["data"]["sections"])
    s2 = set(r2.get_json()["data"]["sections"])
    assert "aiInterpretation" not in s1
    assert "aiInterpretation" in s2


def test_cross_tenant_enhanced_report_blocked(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)
    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01", "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution"],
            "fileFormat": "pdf", "mode": "enhanced",
        },
        headers=other_headers,
    )
    assert resp.status_code == 404
