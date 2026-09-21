"""LLM provider implementations and the factory used by callers.

Provider contract
-----------------
Every provider implements ``LLMProvider.complete`` and returns an
``LLMResult``. The result is always populated; if the call failed the
result has ``status != "ok"`` and a descriptive ``error`` field. The
factory ``get_provider()`` returns the same singleton for the lifetime
of a Flask app context (so unit tests can call ``reset_provider_cache``
to swap implementations).

Failure handling
----------------
The HTTP provider wraps every call in a try/except and maps each
failure mode to a stable status string:

  - ``"unavailable"`` : no key configured, or ``LLM_PROVIDER=disabled``
  - ``"timeout"``     : the request exceeded the configured timeout
  - ``"http_error"``  : non-2xx response from the upstream
  - ``"malformed"``   : the response could not be parsed as JSON, or the
                        completion field was missing
  - ``"exception"``   : any other unhandled failure (logged, never raised)
  - ``"ok"``          : success

This means the rest of the application never has to know about the
specific failure mode — it just checks ``result.status == "ok"``.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result and provider protocol
# ---------------------------------------------------------------------------


@dataclass
class LLMResult:
    """Outcome of a single provider call. Never raises on failure."""

    text: str = ""
    provider: str = ""
    model: str = ""
    status: str = "ok"  # ok | unavailable | timeout | http_error | malformed | exception
    latency_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.text)


class LLMProvider(Protocol):
    """Provider contract. Every implementation must be safe to call from
    any thread (we serialize at the request layer if needed)."""

    name: str

    def is_available(self) -> bool: ...

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResult: ...


# ---------------------------------------------------------------------------
# Deterministic provider — always available, no network, no key.
# ---------------------------------------------------------------------------


class DeterministicProvider:
    """Default provider. Returns a clearly-labelled deterministic string
    so the rest of the pipeline can be exercised end-to-end without any
    LLM dependency. ``status == "ok"`` is reserved for cases where a
    real interpretation is returned; this provider returns status
    ``"unavailable"`` and a ``text`` that says "deterministic fallback"
    so callers can branch on it if they wish.
    """

    name = "deterministic"

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResult:
        # We deliberately do NOT try to "interpret" anything. The whole
        # point is to be the safe fallback that downstream callers can
        # always fall back to. status="unavailable" + a clear text
        # signal lets the report layer render a deterministic note.
        return LLMResult(
            text="(Deterministic fallback — LLM not configured for this environment.)",
            provider=self.name,
            model="deterministic-template",
            status="unavailable",
            latency_ms=0,
            metadata={"fallback": True},
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible HTTP provider — used when LLM_PROVIDER=openai_compatible
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider:
    """HTTP provider for any openai-compatible chat-completions endpoint
    (OpenAI, Azure OpenAI, Together, vLLM, Ollama's /v1/chat/completions,
    LM Studio, etc.).

    Configured entirely from environment:

      LLM_PROVIDER=openai_compatible
      LLM_BASE_URL=https://api.openai.com/v1
      LLM_API_KEY=<secret — never commit>
      LLM_MODEL=gpt-4o-mini
      LLM_TIMEOUT_SECONDS=20
      LLM_MAX_TOKENS=512

    If any required variable is missing, ``is_available()`` returns
    False and every call short-circuits to ``status="unavailable"``.
    """

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int, max_tokens: int):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResult:
        started = time.monotonic()
        if not self.is_available():
            return LLMResult(
                provider=self.name, status="unavailable",
                error="LLM provider is not fully configured (base_url, api_key, model).",
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens or self.max_tokens),
            "stream": False,
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        except requests.Timeout as exc:
            return LLMResult(
                provider=self.name, model=self.model, status="timeout",
                latency_ms=_ms_since(started),
                error=f"LLM request timed out after {self.timeout}s.",
                metadata={"url": self.base_url},
            )
        except requests.RequestException as exc:
            return LLMResult(
                provider=self.name, model=self.model, status="exception",
                latency_ms=_ms_since(started),
                error=str(exc)[:300],
            )

        if resp.status_code < 200 or resp.status_code >= 300:
            return LLMResult(
                provider=self.name, model=self.model, status="http_error",
                latency_ms=_ms_since(started),
                error=f"Upstream returned {resp.status_code}.",
                metadata={"status_code": resp.status_code, "body_excerpt": resp.text[:300]},
            )

        try:
            payload = resp.json()
            text = (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
        except (ValueError, KeyError, IndexError) as exc:
            return LLMResult(
                provider=self.name, model=self.model, status="malformed",
                latency_ms=_ms_since(started),
                error=f"Could not parse response: {exc}",
                metadata={"body_excerpt": resp.text[:300]},
            )

        if not isinstance(text, str) or not text.strip():
            return LLMResult(
                provider=self.name, model=self.model, status="malformed",
                latency_ms=_ms_since(started),
                error="Empty completion.",
                metadata={"payload_keys": list(payload.keys())},
            )

        return LLMResult(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            status="ok",
            latency_ms=_ms_since(started),
            metadata={"usage": payload.get("usage", {})},
        )


# ---------------------------------------------------------------------------
# Stub provider — used by tests to assert the wiring without any HTTP.
# ---------------------------------------------------------------------------


class StubProvider:
    """Programmable provider for tests. Pass ``responses`` to control
    the return sequence. A ``default_text`` is returned when the queue
    is empty. Failures can be injected by passing ``error=...``.
    """

    name = "stub"

    def __init__(self, responses=None, default_text="(stub)", error=None, available=True):
        self._responses = list(responses or [])
        self._default_text = default_text
        self._error = error
        self._available = available
        self.calls = []

    def is_available(self) -> bool:
        return self._available

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResult:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens, "temperature": temperature})
        if not self._available:
            return LLMResult(provider=self.name, status="unavailable", error="stub unavailable")
        if self._error is not None:
            return LLMResult(provider=self.name, status=self._error.get("status", "exception"),
                              error=self._error.get("error", "stub error"))
        if self._responses:
            text = self._responses.pop(0)
        else:
            text = self._default_text
        return LLMResult(text=text, provider=self.name, model="stub-model", status="ok", latency_ms=1)


# ---------------------------------------------------------------------------
# Factory and helpers
# ---------------------------------------------------------------------------


def _ms_since(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _provider_from_env() -> LLMProvider:
    """Read LLM_PROVIDER from environment and instantiate. No I/O."""
    name = (os.environ.get("LLM_PROVIDER") or "deterministic").strip().lower()
    if name in ("", "disabled", "off", "false", "0", "none"):
        return DeterministicProvider()
    if name == "deterministic":
        return DeterministicProvider()
    if name == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            timeout=int(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "512")),
        )
    if name == "stub":
        # Useful for local smoke tests; never default.
        return StubProvider()
    # Unknown provider name -> deterministic fallback with a warning.
    logger.warning("Unknown LLM_PROVIDER=%r; falling back to deterministic", name)
    return DeterministicProvider()


_provider_cache: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    """Return the cached provider. Cache is per-process; tests reset it
    with ``reset_provider_cache()`` to inject stubs."""
    global _provider_cache
    if _provider_cache is None:
        _provider_cache = _provider_from_env()
    return _provider_cache


def reset_provider_cache(provider: Optional[LLMProvider] = None) -> None:
    """Used by tests and by the app factory when config changes."""
    global _provider_cache
    _provider_cache = provider


def is_configured() -> bool:
    """True when the active provider is something other than the
    deterministic fallback. Lets the UI show a clear "LLM enabled"
    indicator without exposing which provider is wired."""
    return get_provider().name != "deterministic" and get_provider().is_available()


def provider_status() -> Dict[str, Any]:
    """Return a small, safe summary of the active provider for the UI
    status panel. Never exposes the API key or the full base URL."""
    p = get_provider()
    base = getattr(p, "base_url", "") or ""
    return {
        "provider": p.name,
        "available": p.is_available(),
        "configured": is_configured(),
        "model": getattr(p, "model", None) or getattr(p, "_default_text", ""),
        "baseUrlHost": _safe_host(base) if base else None,
    }


def _safe_host(url: str) -> Optional[str]:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname
        return host or None
    except Exception:
        return None
