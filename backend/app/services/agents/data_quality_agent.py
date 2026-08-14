"""Read-only reporting agent — no independent validation engine. Reuses the
exact spam/duplicate flags and eligibility rule (app/services/
sentiment_service.py::eligible_reviews_query) every other analysis agent
already relies on. Never deletes or modifies a review.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.models import Review


class DataQualityAgent(BaseAgent):
    name = "data_quality_agent"
    description = "Reports existing review data quality (spam/duplicate/eligible counts). Read-only."
    required_permission = "view_reviews"
    critical = True  # per the Phase 7 brief: a data-quality failure stops downstream analysis

    def run(self, context):
        project_id = context["project_id"]
        base = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))
        total = base.count()
        spam = base.filter(Review.is_spam.is_(True)).count()
        duplicate = base.filter(Review.is_duplicate.is_(True)).count()
        eligible = base.filter(Review.is_spam.is_(False), Review.is_duplicate.is_(False)).count()

        warnings = []
        if total == 0:
            warnings.append("No reviews exist for this project yet.")
        elif eligible == 0:
            warnings.append("No reviews are eligible for analysis (all are spam/duplicate-flagged).")

        return AgentResult(
            self.name, "completed",
            message=f"{total} review(s) total, {eligible} eligible for analysis.",
            data={
                "totalReviews": total, "spamCount": spam,
                "duplicateCount": duplicate, "eligibleForAnalysis": eligible,
            },
            warnings=warnings,
        )
