"""Calls the existing Phase 3 sentiment service directly — no independent
sentiment engine. force=False is the load-bearing detail: run_analysis
only analyses reviews that don't already have a SentimentResult, so a
manually-corrected review (which already has one) is never touched by this
agent — see sentiment_service.py::run_analysis / correct_sentiment.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import sentiment_service


class SentimentAgent(BaseAgent):
    name = "sentiment_agent"
    description = "Runs sentiment analysis on eligible reviews without an existing result."
    required_permission = "view_reviews"
    critical = False

    def run(self, context):
        result = sentiment_service.run_analysis(
            context["project_id"], context["user_id"], force=False,
        )
        warnings = []
        if result["eligibleReviews"] == 0:
            warnings.append("No eligible reviews to analyse.")
        return AgentResult(
            self.name, "completed",
            message=f"Analysed {result['analysedCount']} review(s).",
            data=result, warnings=warnings,
        )
