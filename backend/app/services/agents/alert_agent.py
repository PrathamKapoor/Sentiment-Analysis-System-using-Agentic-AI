"""Calls the existing Phase 5 alert evaluator directly. Evaluates enabled
rules only — never resolves/acknowledges an alert and never sends any
external notification (no such capability exists anywhere in this
codebase to call in the first place).
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import alert_service


class AlertAgent(BaseAgent):
    name = "alert_agent"
    description = "Evaluates enabled alert rules. Never resolves an alert or sends notifications."
    required_permission = "manage_alerts"
    critical = False

    def run(self, context):
        results = alert_service.evaluate_project_alerts(context["project_id"], context["user_id"])
        triggered = sum(1 for r in results if r.get("triggered"))
        return AgentResult(
            self.name, "completed",
            message=f"Evaluated {len(results)} rule(s), {triggered} newly triggered.",
            data={"evaluated": len(results), "triggered": triggered, "items": results},
        )
