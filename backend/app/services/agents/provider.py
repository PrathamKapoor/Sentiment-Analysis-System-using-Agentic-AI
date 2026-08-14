"""Text-generation provider abstraction. Phase 7 ships exactly one
implementation — DeterministicProvider, which just delegates to the
already-completed Phase 5 template engine (app/services/summary_service.py,
recommendation_service.py). No external paid API is mandatory, and none is
configured in this environment.

If a real LLM provider is ever added, it must implement this same
interface and be wrapped so agents never call it directly — see
"Prompt Safety" in README: review/scraped text is always untrusted data,
never instructions, and any future provider must enforce that boundary
here, not in each agent.
"""


class TextGenerationProvider:
    """Interface every provider implements. Agents depend on this
    interface, never on a concrete provider — see get_provider() below.
    """

    name = "base_provider"

    def generate_summary(self, project_id, summary_type, date_from, date_to, actor_user_id):
        raise NotImplementedError

    def is_available(self):
        raise NotImplementedError


class DeterministicProvider(TextGenerationProvider):
    """Wraps the existing deterministic-template summary generator. No
    network calls, no API keys, fully reproducible — same input always
    gives the same output, and every figure traces to a real analytics
    query (see summary_service.py's own module docstring).
    """

    name = "deterministic"

    def is_available(self):
        return True  # always available — this is the guaranteed fallback

    def generate_summary(self, project_id, summary_type, date_from, date_to, actor_user_id):
        from app.services.summary_service import generate_project_summary
        return generate_project_summary(project_id, summary_type, date_from, date_to, actor_user_id)


def get_provider():
    """Single entry point every agent uses. Returns the configured
    provider, or DeterministicProvider if none is configured / the
    configured one reports itself unavailable — this is the fallback-first
    guarantee: the system works with zero AI/LLM configuration.
    """
    # PHASE7_DEFERRED_LLM_PROVIDER: no external provider is implemented or
    # configured in this phase — see docs/phase7_deferred_issues.md. When
    # one exists, select it here based on config and fall back to
    # DeterministicProvider if it reports is_available() == False.
    return DeterministicProvider()
