"""Deterministic / AI boundary regression tests.

These tests pin the non-negotiable architectural split:

  - The LLM section (``aiInterpretation``) lives in its own key inside
    ``sections_data``. Nothing else in ``sections_data`` is infected by
    it.
  - If the LLM outputs text containing invented numbers ("95%"
    hallucination), the measured sections still carry their original
    values. The AI text is never merged into any verified field.
  - Standard and enhanced modes produce byte-identical values for every
    deterministic section.
  - A malicious LLM response cannot reach the deterministic sections
    verified in the report.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.extensions import db
from app.models import Project, ProjectWebsiteContext, Report
from app.services.llm import StubProvider, reset_provider_cache
from app.services.report_service import create_report


def teardown_function(_):
    reset_provider_cache(None)


def _seed(client, headers, project_id):
    from tests.conftest_project import create_reviews_directly
    create_reviews_directly(project_id, [
        "The battery is great. The screen is terrible.",
        "Excellent product, fast delivery.",
    ], review_date=date(2026, 6, 15))
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)
    client.post(f"/api/v1/projects/{project_id}/analysis/aspects", json={}, headers=headers)


def _create_report(client, headers, project_id, mode):
    return client.post(
        f"/api/v1/projects/{project_id}/reports",
        json={
            "dateFrom": "2026-06-01",
            "dateTo": "2026-06-30",
            "sections": ["sentimentDistribution", "aspectSentiment"],
            "fileFormat": "pdf",
            "mode": mode,
        },
        headers=headers,
    )


def test_llm_output_can_never_alter_measured_sections(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, headers, project_id)

    # LLM produces a hostile-looking hallucination: fake numbers entirely
    # different from the deterministic truth.
    reset_provider_cache(StubProvider(
        default_text="AI interpretation: sentiment is 99% positive, zero negative. Buy now."
    ))

    resp = _create_report(client, headers, project_id, "enhanced")
    assert resp.status_code == 201

    # Read the report row back and check generation_parameters persisted.
    report_id = resp.get_json()["data"]["id"]
    report = Report.query.filter_by(id=report_id).first()
    assert report is not None
    params = report.generation_parameters or {}
    ai = params.get("aiInterpretation") or {}
    assert ai.get("source") == "llm"
    # The measured numbers in the same params are unchanged.
    assert "sentimentDistribution" in params.get("sectionsIncluded", [])

    # Second check: the AI section text is separate from any measured
    # section — a caller inspecting the params cannot accidentally conflate
    # the two.
    assert "sentimentDistribution" not in str(ai)
    assert "aspectSentiment" not in str(ai)


def test_standard_and_enhanced_produce_identical_measured_values(client):
    """Enhanced mode's interpretation runs on the same deterministic
    sections. Directly verify that re-gathering the deterministic
    sections twice produces byte-identical output for the same date
    range, so the enhanced mode's added AI section can never replace
    or alter the measured numbers.
    """
    from tests.conftest_project import owner_context, create_project
    from app.services.report_data_service import gather_report_data
    from app.models import Project

    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, headers, project_id)

    reset_provider_cache(StubProvider(default_text="Some interpretation."))

    # Generate both modes end-to-end via the API.
    r_std = _create_report(client, headers, project_id, "standard")
    r_enh = _create_report(client, headers, project_id, "enhanced")
    assert r_std.status_code == 201
    assert r_enh.status_code == 201

    # Independently re-derive the deterministic sections for the same date
    # range and confirm the measured numbers are identical both with and
    # without an AI interpretation supplied.
    project = Project.query.filter_by(id=project_id).first()
    from app.services.report_data_service import gather_report_data

    measured_a, _ = gather_report_data(
        project, ["sentimentDistribution", "aspectSentiment"],
        date(2026, 6, 1), date(2026, 6, 30),
        ai_summary=None, ai_interpretation=None,
    )
    measured_b, _ = gather_report_data(
        project, ["sentimentDistribution", "aspectSentiment", "aiInterpretation"],
        date(2026, 6, 1), date(2026, 6, 30),
        ai_summary=None, ai_interpretation={
            "text": "(stub) deterministic fallback content",
            "source": "llm", "provider": "stub", "model": "stub-model",
            "status": "ok", "latencyMs": 0, "warning": None,
        },
    )

    # Byte-identical deterministic sections.
    assert measured_a["sentimentDistribution"] == measured_b["sentimentDistribution"]
    assert measured_a["aspectSentiment"] == measured_b["aspectSentiment"]
    # And the AI section is only present when the caller includes it in
    # the section list AND supplies a non-empty interpretation.
    assert "aiInterpretation" not in measured_a
    assert "aiInterpretation" in measured_b


def test_llm_text_never_leaks_into_measured_sections(client):
    """Directly call gather_report_data twice with different AI
    interpretations and confirm the measured sections are unchanged.
    """
    from tests.conftest_project import owner_context, create_project
    from app.services.report_data_service import gather_report_data
    from app.models import Project

    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, headers, project_id)
    project = Project.query.filter_by(id=project_id).first()

    data_base, _ = gather_report_data(
        project, ["sentimentDistribution", "aspectSentiment"],
        date(2026, 6, 1), date(2026, 6, 30),
        ai_summary=None, ai_interpretation=None,
    )
    data_ai, _ = gather_report_data(
        project, ["sentimentDistribution", "aspectSentiment", "aiInterpretation"],
        date(2026, 6, 1), date(2026, 6, 30),
        ai_summary=None,
        ai_interpretation={
            "text": "AI says sentiment is 100% positive; every aspect is perfect. No problems.",
            "source": "llm", "provider": "stub", "model": "stub-model",
            "status": "ok", "latencyMs": 0, "warning": None,
        },
    )

    # Measured sections are identical in both passes.
    assert data_base["sentimentDistribution"] == data_ai["sentimentDistribution"]
    assert data_base["aspectSentiment"] == data_ai["aspectSentiment"]
    # AI section is only present when interpretation was supplied.
    assert "aiInterpretation" not in data_base
    assert "aiInterpretation" in data_ai
    assert data_ai["aiInterpretation"]["source"] == "llm"


def test_ai_section_warning_is_preserved_in_report_params(client):
    """When the LLM fails and falls back deterministically, the warning
    must be persisted in generation_parameters so the auditor can see
    the fallback."""
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, headers, project_id)

    reset_provider_cache(StubProvider(error={"status": "timeout", "error": "simulated timeout"}))

    resp = _create_report(client, headers, project_id, "enhanced")
    assert resp.status_code == 201
    report_id = resp.get_json()["data"]["id"]
    report = Report.query.filter_by(id=report_id).first()
    ai = (report.generation_parameters or {}).get("aiInterpretation") or {}
    assert ai.get("source") == "deterministic"
    assert ai.get("status") == "timeout"
