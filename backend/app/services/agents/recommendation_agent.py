"""Calls the existing Phase 4 recommendation service directly. Generated
recommendations always land in status="new" (advisory) — this agent never
accepts/rejects/assigns them; only a human via the existing accept/reject
endpoints (approve_ai_output permission) can change that status.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import recommendation_service


class RecommendationAgent(BaseAgent):
    name = "recommendation_agent"
    description = "Generates advisory rule-based recommendations. Never accepts/rejects them itself."
    required_permission = "view_reviews"
    critical = False

    def run(self, context):
        params = context.get("parameters") or {}
        created = recommendation_service.generate_recommendations(
            context["project_id"], context["user_id"], min_frequency=params.get("minFrequency"),
        )
        return AgentResult(
            self.name, "completed",
            message=f"Generated {len(created)} new recommendation(s) — advisory, human accept/reject required.",
            data={"createdCount": len(created), "items": [r.to_dict() for r in created]},
        )
