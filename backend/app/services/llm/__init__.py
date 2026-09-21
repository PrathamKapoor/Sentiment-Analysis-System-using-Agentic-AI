"""LLM provider layer — optional, opt-in, env-driven.

Why this exists
---------------
The deterministic analytics layer (sentiment, aspect, topic, trend) is
always the source of truth. This package is the *interpretation* layer
that an authorised user can switch on to enrich reports with narrative
context. It must:

  1. Work fully without any API key — a deterministic provider is the
     default and is always available.
  2. Never block the report path — if the configured provider is
     unavailable, times out, returns malformed JSON, or refuses, the
     caller degrades to a deterministic fallback.
  3. Be auditable — every call records provider name, model, latency, and
     a short status (`ok`, `unavailable`, `timeout`, `malformed`).
  4. Never see prompts that contain raw review text in a way that lets a
     remote provider reconstruct a full review corpus — see
     ``prompt_builder`` for what is sent.
  5. Be safe by default — no hard-coded keys, no hard-coded endpoints,
     every network call goes through ``requests`` with explicit timeout
     and is bound to environment variables.

Public surface used by callers
------------------------------
  - ``get_provider()`` -> ``LLMProvider`` (factory)
  - ``LLMProvider.complete(prompt, *, system=None, max_tokens=512,
    temperature=0.2)`` -> ``LLMResult``
  - ``LLMResult`` (text, provider, model, status, latency_ms, error)
  - ``is_configured()`` -> bool (True if an LLM is wired and ready)

The LLM is **only** invoked by the report layer when a report is
generated in ``enhanced`` mode. It is never invoked for routine analysis,
collection, or workflow steps.
"""
from app.services.llm.provider import (
    LLMProvider,
    LLMResult,
    DeterministicProvider,
    OpenAICompatibleProvider,
    StubProvider,
    is_configured,
    get_provider,
    reset_provider_cache,
)

__all__ = [
    "LLMProvider",
    "LLMResult",
    "DeterministicProvider",
    "OpenAICompatibleProvider",
    "StubProvider",
    "is_configured",
    "get_provider",
    "reset_provider_cache",
]
