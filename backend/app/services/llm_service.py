"""Public LLM service — the only entry point the rest of the app uses.

This module glues together:

  - ``app.services.llm.provider`` (provider factory)
  - ``app.services.llm.prompt_builder`` (structured prompt construction)
  - ``app.services.llm.fallback_interpretation`` (deterministic fallback)

Callers (currently only the report layer) call
``interpret_analytics(analytics, business_context=...)`` and get back a
small dict with ``text``, ``source`` (one of ``"llm"`` / ``"deterministic"``),
``provider``, ``status``, ``latency_ms``, and an optional ``warning``.

Design rules
------------
  - Never raise on LLM failure. Always return a usable text.
  - The deterministic fallback is always available and always labelled.
  - Callers cannot tell whether the LLM was invoked or not by looking at
    the exception path — they look at ``result["source"]``.
  - Audit logging is best-effort; it never blocks the response.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

# Hard bound on LLM-generated text length. Prevents a hostile or
# malfunctioning provider from bloating a report or crash the renderer.
LLM_OUTPUT_MAX_CHARS = 8000
# Allow line-break recovery, strip control characters but keep
# \n and \t.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_llm_text(text: Any) -> str:
    """Bound, normalise, and defensively clean LLM output before it
    is stored or rendered. Never raise."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""
    if len(text) > LLM_OUTPUT_MAX_CHARS:
        text = text[:LLM_OUTPUT_MAX_CHARS]
    text = _CONTROL_CHARS.sub("", text)
    return text

from app.services.llm.fallback_interpretation import generate_deterministic_interpretation
from app.services.llm.prompt_builder import build_prompt
from app.services.llm.provider import get_provider

logger = logging.getLogger(__name__)


def _log_llm_call(
    *,
    actor_user_id: Optional[str],
    organisation_id: Optional[str],
    project_id: Optional[str],
    source: str,
    status: str,
    provider: str,
    model: str,
    latency_ms: int,
    error: Optional[str] = None,
) -> None:
    """Best-effort audit log entry. Never raises. The audit_log table
    is not the right place for a high-volume trace; this is a single
    line per report-time interpretation call. When the caller does not
    have an authenticated user/org (e.g. background tasks, tests), the
    audit row is silently skipped — the LLM call still proceeds and
    the caller still gets a result.
    """
    if not actor_user_id or not organisation_id:
        return  # nothing useful to log
    try:
        from app.services.audit_service import log_action
        # log_action signature: (organisation_id, actor_id, action, entity_type, entity_id, metadata)
        log_action(
            organisation_id,
            actor_user_id,
            "llm.interpretation",
            "project",
            str(project_id) if project_id else "",
            {
                "source": source,
                "status": status,
                "provider": provider,
                "model": model,
                "latencyMs": latency_ms,
                "error": (error or "")[:200] or None,
            },
        )
    except Exception as exc:  # never let audit break a report
        logger.debug("LLM audit log skipped: %s", exc)


def interpret_analytics(
    analytics: Dict[str, Any],
    *,
    business_context: Optional[Dict[str, Any]] = None,
    max_tokens: int = 512,
    temperature: float = 0.2,
    actor_user_id: Optional[str] = None,
    organisation_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the LLM if available, otherwise return a deterministic
    interpretation. Never raises.

    The return shape is stable so the report layer can render either
    result with a single template path:

      {
        "text":   "<the interpretation>",
        "source": "llm" | "deterministic",
        "provider": "<provider name>",
        "model":   "<model name or 'deterministic-template'>",
        "status":  "ok" | "unavailable" | "timeout" | "http_error" | "malformed" | "exception",
        "latencyMs": 123,
        "warning": "<optional human-readable note for the UI>"
      }
    """
    provider = get_provider()
    if not provider.is_available() or provider.name == "deterministic":
        result = {
            "text": generate_deterministic_interpretation(analytics or {}),
            "source": "deterministic",
            "provider": provider.name,
            "model": "deterministic-template",
            "status": "ok",
            "latencyMs": 0,
            "warning": "LLM is not configured for this environment. A deterministic interpretation was generated from the verified metrics.",
        }
        _log_llm_call(
            actor_user_id=actor_user_id,
            organisation_id=organisation_id,
            project_id=project_id,
            source=result["source"],
            status=result["status"],
            provider=result["provider"],
            model=result["model"],
            latency_ms=0,
        )
        return result

    system, user = build_prompt(analytics or {}, business_context=business_context)
    call_result = provider.complete(
        user,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    if call_result.ok:
        # Sanitise before persisting; the report renderers see this text.
        cleaned = _sanitize_llm_text(call_result.text)
        if cleaned:
            result = {
                "text": cleaned,
                "source": "llm",
                "provider": call_result.provider,
                "model": call_result.model,
                "status": "ok",
                "latencyMs": call_result.latency_ms,
                "warning": None,
            }
        else:
            # Empty completion counts as malformed; fall through to the
            # deterministic branch below so the report still completes.
            call_result.status = "malformed"
            call_result.error = "empty_completion"

    if not call_result.ok:
        # Deterministic fallback on any failure mode.
        result = {
            "text": generate_deterministic_interpretation(analytics or {}),
            "source": "deterministic",
            "provider": call_result.provider,
            "model": call_result.model or "deterministic-template",
            "status": call_result.status,
            "latencyMs": call_result.latency_ms,
            "warning": _friendly_warning(call_result.status, call_result.error),
        }

    _log_llm_call(
        actor_user_id=actor_user_id,
        organisation_id=organisation_id,
        project_id=project_id,
        source=result["source"],
        status=result["status"],
        provider=result["provider"],
        model=result["model"],
        latency_ms=result["latencyMs"],
        error=call_result.error if not call_result.ok else None,
    )
    return result


def _friendly_warning(status: str, error: Optional[str]) -> str:
    if status == "timeout":
        return "The configured LLM provider timed out. A deterministic interpretation has been used."
    if status == "http_error":
        return "The configured LLM provider returned an error. A deterministic interpretation has been used."
    if status == "malformed":
        return "The configured LLM provider returned an unparseable response. A deterministic interpretation has been used."
    if status == "exception":
        return "The configured LLM provider is unreachable. A deterministic interpretation has been used."
    if status == "unavailable":
        return "The configured LLM provider is not available. A deterministic interpretation has been used."
    return "LLM call did not succeed. A deterministic interpretation has been used."


def provider_summary() -> Dict[str, Any]:
    """Return a UI-safe summary of the active provider. Safe to expose
    to any authenticated user. No secrets."""
    from app.services.llm.provider import provider_status
    return provider_status()
