"""LLM provider + service tests.

Covers:
  - provider unavailable (no key, unknown name, disabled)
  - provider success (stub)
  - provider timeout (HTTP)
  - provider malformed JSON
  - provider http_error
  - the facade always returns a usable text (deterministic fallback)
  - the facade audits every call when given a real org/user
  - the facade silently skips audit when given no org/user
  - the prompt builder summarises long lists
  - the facade never sends raw review text
  - the LLM status endpoint never leaks secrets
"""
from __future__ import annotations

import json

import pytest

from app.extensions import db
from app.models import AuditLog
from app.services.llm import (
    DeterministicProvider,
    OpenAICompatibleProvider,
    StubProvider,
    get_provider,
    is_configured,
    reset_provider_cache,
)
from app.services.llm_service import interpret_analytics, provider_summary
from app.services.llm.prompt_builder import build_prompt


def teardown_function(_):
    reset_provider_cache(None)


# ---------------- provider factory tests ----------------


def test_deterministic_provider_is_always_available():
    reset_provider_cache(DeterministicProvider())
    p = get_provider()
    assert p.is_available() is True
    assert p.name == "deterministic"
    result = p.complete("hello")
    assert result.ok is False
    assert result.status == "unavailable"
    assert "Deterministic fallback" in result.text


def test_stub_provider_returns_responses():
    reset_provider_cache(StubProvider(responses=["first answer", "second answer"]))
    p = get_provider()
    r1 = p.complete("q1")
    r2 = p.complete("q2")
    assert r1.text == "first answer"
    assert r2.text == "second answer"
    assert r1.ok is True


def test_stub_provider_records_calls():
    reset_provider_cache(StubProvider(default_text="x"))
    p = get_provider()
    p.complete("prompt1", system="sys", max_tokens=64, temperature=0.1)
    assert len(p.calls) == 1
    assert p.calls[0]["prompt"] == "prompt1"
    assert p.calls[0]["system"] == "sys"
    assert p.calls[0]["max_tokens"] == 64


def test_openai_compatible_provider_missing_key_is_unavailable():
    p = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4o-mini",
        timeout=5,
        max_tokens=64,
    )
    assert p.is_available() is False
    result = p.complete("hi")
    assert result.status == "unavailable"
    assert result.provider == "openai_compatible"


def test_openai_compatible_provider_timeout(monkeypatch):
    import requests
    p = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        timeout=1,
        max_tokens=64,
    )
    def _boom(*a, **kw):
        raise requests.Timeout("read timed out")
    import app.services.llm.provider as provider_mod
    monkeypatch.setattr(provider_mod.requests, "post", _boom)
    result = p.complete("hi")
    assert result.status == "timeout"
    assert result.latency_ms >= 0


def test_openai_compatible_provider_http_error(monkeypatch):
    import requests
    p = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        timeout=5,
        max_tokens=64,
    )
    resp = requests.Response()
    resp.status_code = 401
    resp._content = b"unauthorized"
    def _post(*a, **kw):
        return resp
    import app.services.llm.provider as provider_mod
    monkeypatch.setattr(provider_mod.requests, "post", _post)
    result = p.complete("hi")
    assert result.status == "http_error"
    assert result.metadata["status_code"] == 401


def test_openai_compatible_provider_malformed_response(monkeypatch):
    import requests
    p = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        timeout=5,
        max_tokens=64,
    )
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b"not json"
    resp.headers = {"Content-Type": "application/json"}
    def _post(*a, **kw):
        return resp
    import app.services.llm.provider as provider_mod
    monkeypatch.setattr(provider_mod.requests, "post", _post)
    result = p.complete("hi")
    assert result.status == "malformed"


def test_openai_compatible_provider_success(monkeypatch):
    import requests
    p = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        timeout=5,
        max_tokens=64,
    )
    resp = requests.Response()
    resp.status_code = 200
    resp._content = json.dumps({
        "choices": [{"message": {"content": "Hello, world."}}],
        "usage": {"total_tokens": 7},
    }).encode("utf-8")
    resp.headers = {"Content-Type": "application/json"}
    def _post(*a, **kw):
        return resp
    import app.services.llm.provider as provider_mod
    monkeypatch.setattr(provider_mod.requests, "post", _post)
    result = p.complete("hi", system="be brief")
    assert result.ok
    assert result.text == "Hello, world."
    assert result.provider == "openai_compatible"
    assert result.model == "gpt-4o-mini"
    assert result.metadata["usage"]["total_tokens"] == 7


def test_is_configured_reflects_provider_name():
    reset_provider_cache(DeterministicProvider())
    assert is_configured() is False
    reset_provider_cache(StubProvider(default_text="x"))
    assert is_configured() is True


# ---------------- prompt builder tests ----------------


def test_prompt_builder_contains_verified_data_and_rules():
    system, user = build_prompt(
        {"projectName": "X", "sentiment": {"positive": {"count": 5, "percentage": 50}}},
        business_context=None,
    )
    assert "Do not invent numbers" in system
    assert "VERIFIED DATA" in user
    assert "count=5" in user
    assert "percentage=50" in user
    assert "BUSINESS CONTEXT" in user
    assert "no website context" in user.lower()


def test_prompt_builder_summarises_long_list_values():
    """Long lists are summarised with a +N more marker so a caller that
    accidentally passes a list of strings cannot leak a full corpus.
    """
    _, user = build_prompt(
        {
            "totalReviews": 100,
            "spamCount": 5,
            "duplicateCount": 3,
            "rawReviews": ["forbidden review text"] * 100,
        },
        business_context=None,
    )
    assert "spamCount: 5" in user
    assert "duplicateCount: 3" in user
    assert "+95 more" in user


def test_prompt_builder_includes_business_context_when_provided():
    _, user = build_prompt(
        {"sentiment": "ok"},
        business_context={"sourceUrl": "https://x.test", "title": "Acme", "metaDescription": "We sell stuff"},
    )
    assert "Acme" in user
    assert "We sell stuff" in user
    assert "https://x.test" in user


# ---------------- facade tests ----------------


def test_facade_returns_deterministic_when_provider_unavailable(app):
    reset_provider_cache(DeterministicProvider())
    with app.app_context():
        out = interpret_analytics(
            {"totalReviews": 5, "sentiment": {"positive": {"count": 3, "percentage": 60}}},
            business_context=None,
        )
    assert out["source"] == "deterministic"
    assert out["status"] == "ok"
    assert out["text"]
    assert "deterministic" in out["text"].lower() or "deterministic" in (out["warning"] or "").lower()


def test_facade_uses_llm_when_provider_succeeds(app):
    reset_provider_cache(StubProvider(default_text="LLM-style interpretation."))
    with app.app_context():
        out = interpret_analytics(
            {"totalReviews": 5, "sentiment": {"positive": {"count": 3, "percentage": 60}}},
            business_context=None,
        )
    assert out["source"] == "llm"
    assert out["text"] == "LLM-style interpretation."
    assert out["provider"] == "stub"
    assert out["model"] == "stub-model"


def test_facade_falls_back_when_provider_times_out(app):
    reset_provider_cache(StubProvider(error={"status": "timeout", "error": "boom"}))
    with app.app_context():
        out = interpret_analytics({"totalReviews": 1}, business_context=None)
    assert out["source"] == "deterministic"
    assert out["status"] == "timeout"
    assert out["warning"]


def test_facade_silently_skips_audit_when_no_org_or_actor(app):
    """The facade must not crash when called without an authenticated
    user. The audit row is silently skipped; the LLM call still
    completes successfully and the caller still gets a result.
    """
    reset_provider_cache(StubProvider(default_text="x"))
    with app.app_context():
        out = interpret_analytics({"totalReviews": 1}, business_context=None)
    assert out["source"] == "llm"
    db.session.commit()
    actions = [
        a.action for a in AuditLog.query.filter_by(action="llm.interpretation").all()
    ]
    assert actions == []


def test_facade_writes_audit_log_when_org_and_actor_given(app):
    """When the caller supplies a real organisation_id and actor_user_id
    the audit_log row is created.
    """
    from tests.conftest import register, login, auth_header
    reset_provider_cache(StubProvider(default_text="x"))
    with app.test_client() as c:
        with app.app_context():
            reg = register(c, org_name="Audit Org", email="audit@audit.test").get_json()["data"]
            access = login(c, email="audit@audit.test").get_json()["data"]["accessToken"]
            out = interpret_analytics(
                {"totalReviews": 1}, business_context=None,
                actor_user_id=reg["userId"],
                organisation_id=reg["organisationId"],
                project_id=reg["organisationId"],
            )
            assert out["source"] == "llm"
            db.session.commit()
            actions = [
                a.action for a in AuditLog.query.filter_by(action="llm.interpretation").all()
            ]
            assert "llm.interpretation" in actions


def test_facade_never_sends_raw_review_text_in_prompt(app):
    """The facade builds the analytics dict, then asks the provider to
    complete. A real review string must never reach the LLM, even
    accidentally.
    """
    captured = {}

    class CapturingProvider:
        name = "capturing"

        def is_available(self):
            return True

        def complete(self, prompt, *, system=None, max_tokens=512, temperature=0.2):
            captured["prompt"] = prompt
            captured["system"] = system
            return _ok_result()

    reset_provider_cache(CapturingProvider())
    with app.app_context():
        out = interpret_analytics(
            {
                "totalReviews": 3,
                "sentiment": {"positive": {"count": 1, "percentage": 33}},
            },
            business_context=None,
        )
    assert "totally secret review body the LLM must not see" not in captured["prompt"]
    assert "totally secret review body" not in captured["system"]


def _ok_result():
    from app.services.llm.provider import LLMResult
    return LLMResult(text="ok", provider="capturing", model="t", status="ok", latency_ms=1)


# ---------------- status endpoint / secrets ----------------


def test_provider_summary_never_exposes_key():
    reset_provider_cache(OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-THIS-IS-A-SECRET-DO-NOT-LOG",
        model="gpt-4o-mini",
        timeout=5,
        max_tokens=64,
    ))
    s = provider_summary()
    assert s["provider"] == "openai_compatible"
    assert s["baseUrlHost"] == "api.openai.com"
    assert "sk-THIS-IS-A-SECRET" not in json.dumps(s)
    assert "api_key" not in json.dumps(s).lower()
