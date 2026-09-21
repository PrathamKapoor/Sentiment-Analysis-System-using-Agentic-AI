"""Observability, aspect-negation, and pluggable sentiment engine tests."""
from __future__ import annotations

import logging
import time

import pytest

from app.services.observability import (
    REQUEST_ID_HEADER,
    get_or_create_request_id,
    step_timer,
    structured_log,
)
from app.services.sentiment_analyzer import (
    StubLexiconSentimentAnalyzer,
    VaderSentimentAnalyzer,
    current_engine_name,
    get_analyzer,
    reset_analyzer_cache,
)
from app.services.aspect_analyzer import AspectAnalyzer


# ---------------- observability ----------------


def test_request_id_assigned_in_request_context(client):
    """Inside a request, the response has an X-Request-ID header."""
    resp = client.get("/api/v1/health")
    assert resp.status_code in (200, 404)
    rid = resp.headers.get(REQUEST_ID_HEADER)
    assert rid and len(rid) >= 8


def test_request_id_propagates_from_incoming_header(client):
    rid_in = "abc-1234-xyz"
    resp = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: rid_in})
    assert resp.status_code in (200, 404)
    assert resp.headers.get(REQUEST_ID_HEADER) == rid_in


def test_step_timer_records_duration():
    rec = {}
    with step_timer("unit", metadata={"k": "v"}) as t:
        rec["timer"] = t
        time.sleep(0.01)
    assert t["name"] == "unit"
    assert t["durationMs"] is not None and t["durationMs"] >= 8
    assert t["finishedAt"] is not None
    assert t["metadata"] == {"k": "v"}


def test_structured_log_does_not_raise():
    logger = logging.getLogger("test_structured_log")
    structured_log(logger, "hello", level=logging.INFO, actor_user_id="u1", project_id="p1", org="o1")
    structured_log(logger, "warn", level=logging.WARNING, project_id="p1")
    assert True


# ---------------- aspect analyzer shape ----------------


def test_aspect_analyzer_returns_transparency_fields():
    """The analyser returns transparency fields (compound, evidence_text)
    on every call, so callers can audit the local-context signal.
    """
    a = AspectAnalyzer()
    out = a.analyse_aspect_sentiment("The battery is great", "battery")
    assert "label" in out
    assert "confidence_score" in out
    assert "compound" in out
    assert "evidence_text" in out
    # No post-correction flags — Phase 10 audit removed them because the
    # heuristic produced false positives ("The battery never fails.").
    assert "negation_hint_applied" not in out


def test_aspect_evidence_text_is_truncated():
    a = AspectAnalyzer()
    text = "The screen is bright " + ("and vivid " * 60) + "and clear."
    out = a.analyse_aspect_sentiment(text, "screen")
    assert "truncated" in (out["evidence_text"] or "").lower()


def test_aspect_negation_is_vaders_job_alone():
    """The one-line audit verdict from Phase 10: the analyser must defer
    negation handling entirely to VADER. No post-correction flip.
    """
    a = AspectAnalyzer()
    cases = [
        ("The battery never fails.", "positive"),
        ("The battery is not good.", "negative"),
        ("Not only was the service good, it was excellent.", "positive"),
        ("The battery is fantastic.", "positive"),
        ("The battery is terrible.", "negative"),
    ]
    for text, expected in cases:
        out = a.analyse_aspect_sentiment(text, "battery" if "battery" in text.lower() else "service")
        assert out["label"] == expected, f"{text!r} → {out['label']} (expected {expected})"


# ---------------- pluggable sentiment engine ----------------


def test_default_engine_is_vader():
    reset_analyzer_cache(None)
    a = get_analyzer()
    assert isinstance(a, VaderSentimentAnalyzer)
    assert current_engine_name() == "vader"


def test_stub_lexicon_engine_is_loaded_when_requested(monkeypatch):
    monkeypatch.setenv("SENTIMENT_ENGINE", "stub")
    reset_analyzer_cache(None)
    a = get_analyzer()
    assert isinstance(a, StubLexiconSentimentAnalyzer)
    assert current_engine_name() == "stub"
    out = a.analyze("This is great and amazing")
    assert out["label"] == "positive"
    assert out["model_name"] == "stub-lexicon"
    reset_analyzer_cache(None)


def test_unknown_engine_name_falls_back_to_vader(monkeypatch):
    monkeypatch.setenv("SENTIMENT_ENGINE", "this-does-not-exist")
    reset_analyzer_cache(None)
    a = get_analyzer()
    assert isinstance(a, VaderSentimentAnalyzer)
    reset_analyzer_cache(None)


def test_vader_analyzer_breakdown_shape_unchanged():
    a = VaderSentimentAnalyzer()
    out = a.analyze("The service is great and the price is awful")
    assert "label" in out
    assert "compound" in out
    assert "positive_score" in out
    assert "negative_score" in out
    assert "neutral_score" in out
    assert "confidence_score" in out
    assert "model_name" in out
    assert "model_version" in out
    assert "vader_breakdown" in out
    breakdown = out["vader_breakdown"]
    assert "tokens" in breakdown
    assert "contributingTerms" in breakdown
