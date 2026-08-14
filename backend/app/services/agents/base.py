"""Shared agent contract. Every agent is a thin wrapper around an existing,
already-tested service — see the module docstring in each agent file for
which service it calls. Agents never implement independent business logic
(no second sentiment engine, no second topic clusterer, etc).
"""

STATUSES = ("pending", "running", "completed", "failed", "skipped", "waiting_for_approval")


class AgentResult:
    def __init__(self, agent, status, message="", data=None, warnings=None):
        if status not in STATUSES:
            raise ValueError(f"Invalid agent status: {status}")
        self.agent = agent
        self.status = status
        self.message = message
        self.data = data or {}
        self.warnings = warnings or []

    def to_dict(self):
        return {
            "agent": self.agent,
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "warnings": self.warnings,
        }


class BaseAgent:
    """context is always:
    {
      "organisation_id": ..., "project_id": ..., "user_id": ...,
      "membership": <OrganisationMember>, "workflow_id": ...,
      "parameters": {...this-agent-specific options...},
    }
    Never trust IDs from anywhere else (e.g. would-be LLM output) — the
    orchestrator builds this context once from the authenticated request,
    and every agent (and the service it calls) re-validates tenant scope
    independently — defense in depth, same as every other service in this
    codebase.
    """

    name = "base_agent"
    description = ""
    required_permission = None  # None = no permission gate (read-only reporting agents)
    supports_dry_run = False
    critical = False  # if True, this agent's failure stops the whole workflow

    def can_run(self, context):
        """Returns (bool, reason_or_none). Never raises — a missing
        permission is reported as "skipped", not a hard error, so the rest
        of the workflow can still proceed (see README "Permissions").
        """
        if self.required_permission is None:
            return True, None
        membership = context.get("membership")
        if membership is None:
            return False, "No organisation membership context."
        from app.services.permission_service import has_permission
        if not has_permission(membership, self.required_permission):
            return False, f"Missing required permission: {self.required_permission}"
        return True, None

    def validate_input(self, context):
        if not context.get("project_id") or not context.get("organisation_id"):
            raise ValueError("Agent context must include project_id and organisation_id")

    def run(self, context):
        raise NotImplementedError

    def handle_failure(self, exc, context):
        return AgentResult(self.name, "failed", message=str(exc)[:500])

    def execute(self, context):
        """The one method the orchestrator calls."""
        allowed, reason = self.can_run(context)
        if not allowed:
            return AgentResult(self.name, "skipped", message=reason)
        try:
            self.validate_input(context)
            return self.run(context)
        except Exception as exc:
            return self.handle_failure(exc, context)
