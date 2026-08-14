"""Calls the existing Phase 4 aspect service directly — no independent
extraction logic, no reintroduced fields Phase 4 deliberately excluded
(aspects stores only id/project_id/name; aspect_sentiments only
review_id/aspect_id/sentiment_label/confidence_score — see aspect
model docstrings). force=False preserves prior results the same way
sentiment_agent does.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import aspect_service


class AspectAgent(BaseAgent):
    name = "aspect_agent"
    description = "Runs aspect-based sentiment extraction over eligible reviews."
    required_permission = "view_reviews"
    critical = False

    def run(self, context):
        result = aspect_service.run_aspect_analysis(
            context["project_id"], context["user_id"], force=False,
        )
        warnings = []
        if result["eligibleReviews"] == 0:
            warnings.append("No eligible reviews to analyse for aspects.")
        return AgentResult(
            self.name, "completed",
            message=f"Analysed {result['reviewsAnalysed']} review(s), "
                    f"{result['aspectLinksCreated']} aspect link(s) created.",
            data=result, warnings=warnings,
        )
