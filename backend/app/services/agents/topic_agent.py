"""Calls the existing Phase 3 topic service directly — no independent
clustering logic. An insufficient-data ValidationError (fewer than 2
eligible reviews with usable text) is treated as "skipped", not "failed" —
this is expected, benign behavior for a small project, not an error.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import topic_service
from app.errors.exceptions import ValidationError


class TopicAgent(BaseAgent):
    name = "topic_agent"
    description = "Runs topic clustering (TF-IDF + MiniBatchKMeans) over eligible reviews."
    required_permission = "view_reviews"
    critical = False

    def run(self, context):
        params = context.get("parameters") or {}
        try:
            result = topic_service.run_topic_analysis(
                context["project_id"], context["organisation_id"], context["user_id"],
                topic_count=params.get("topicCount"),
            )
        except ValidationError as exc:
            return AgentResult(self.name, "skipped", message=exc.message)

        return AgentResult(
            self.name, "completed",
            message=f"Clustered {result.get('reviewsClustered', 0)} review(s) into "
                    f"{result.get('topicCount', 0)} topic(s).",
            data=result,
        )
