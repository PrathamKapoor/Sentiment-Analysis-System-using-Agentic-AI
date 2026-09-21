"""Gathers report content from existing analytics services — nothing is
computed specially for reports; every number is the same one already shown
on the corresponding analysis page. Sections with no underlying data are
omitted from the report (never fabricated), and reported back as
`sectionsSkipped` so the caller knows what was left out and why.
"""
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.models import Review, Alert
from app.services import (
    sentiment_service, topic_service, keyword_service, aspect_service,
    recommendation_service, trend_service,
)

# A report section that holds AI-generated interpretation, never raw
# numbers. Only included when the report is generated in ``enhanced``
# mode AND the caller passed an ``ai_interpretation`` dict.
AI_INTERPRETATION_SECTION = "aiInterpretation"

ALL_SECTIONS = (
    "projectOverview", "executiveSummary", "sentimentDistribution", "sentimentTrends",
    "topicAnalysis", "keywordAnalysis", "aspectSentiment", "recommendations",
    "comparison", "alerts", "representativeReviews", "conclusion",
    AI_INTERPRETATION_SECTION,
)


def gather_report_data(
    project,
    sections,
    date_from,
    date_to,
    ai_summary=None,
    ai_interpretation: Optional[Dict[str, Any]] = None,
):
    filters = {"dateFrom": date_from, "dateTo": date_to}
    data = {}
    skipped = []
    max_rows = current_app.config.get("MAX_REPORT_REVIEW_ROWS", 500)

    if "projectOverview" in sections:
        data["projectOverview"] = {
            "name": project.name, "description": project.description,
            "status": project.status, "dateRangeStart": str(date_from), "dateRangeEnd": str(date_to),
        }

    if "executiveSummary" in sections:
        if ai_summary:
            data["executiveSummary"] = ai_summary.content.get("sections", {}).get("overall")
        else:
            skipped.append("executiveSummary")

    if "sentimentDistribution" in sections:
        summary = sentiment_service.get_summary(project.id, filters)
        if summary["analysedReviews"] > 0:
            data["sentimentDistribution"] = summary
        else:
            skipped.append("sentimentDistribution")

    if "sentimentTrends" in sections:
        trends = trend_service.get_trends(project.id, "monthly", filters)
        if trends["periods"]:
            data["sentimentTrends"] = trends
        else:
            skipped.append("sentimentTrends")

    if "topicAnalysis" in sections:
        topics = topic_service.list_topics(project.id)
        if topics:
            data["topicAnalysis"] = [{"topicName": t.name, "reviewCount": t.review_count} for t in topics]
        else:
            skipped.append("topicAnalysis")

    if "keywordAnalysis" in sections:
        keywords = keyword_service.extract_keywords(project.id, filters=filters, top_n=20)
        if keywords:
            data["keywordAnalysis"] = keywords
        else:
            skipped.append("keywordAnalysis")

    if "aspectSentiment" in sections:
        aspects = aspect_service.list_aspects(project.id, filters)
        if aspects:
            data["aspectSentiment"] = aspects
        else:
            skipped.append("aspectSentiment")

    if "recommendations" in sections:
        recs = recommendation_service.list_recommendations(project.id)
        if recs:
            data["recommendations"] = [r.to_dict() for r in recs]
        else:
            skipped.append("recommendations")

    if "comparison" in sections:
        # Comparison requires an explicit target project list — not
        # meaningful as a single-project report section without one.
        skipped.append("comparison")

    if "alerts" in sections:
        alerts = Alert.query.filter_by(project_id=project.id).all()
        if alerts:
            data["alerts"] = [a.to_dict() for a in alerts]
        else:
            skipped.append("alerts")

    if "representativeReviews" in sections:
        reviews = (
            Review.query.filter_by(project_id=project.id)
            .order_by(Review.created_at.desc())
            .limit(max_rows).all()
        )
        if reviews:
            data["representativeReviews"] = [{"text": r.text, "rating": r.rating, "date": str(r.review_date) if r.review_date else None} for r in reviews]
        else:
            skipped.append("representativeReviews")

    if "conclusion" in sections:
        sentiment = data.get("sentimentDistribution")
        aspects = data.get("aspectSentiment")
        if sentiment and aspects:
            dominant = max(sentiment["positive"], sentiment["negative"], sentiment["neutral"], key=lambda x: x["count"]) if sentiment else None
            top_aspect = aspects[0]["name"] if aspects else None
            data["conclusion"] = (
                f"Based on {sentiment['analysedReviews']} reviews, the dominant sentiment is "
                f"{dominant['label']} ({dominant['percentage']}%). The most-discussed aspect is "
                f"\"{top_aspect}\"."
            )
        else:
            skipped.append("conclusion")

    if AI_INTERPRETATION_SECTION in sections:
        if ai_interpretation and ai_interpretation.get("text"):
            data[AI_INTERPRETATION_SECTION] = {
                "text": ai_interpretation.get("text", ""),
                "source": ai_interpretation.get("source", "deterministic"),
                "provider": ai_interpretation.get("provider"),
                "model": ai_interpretation.get("model"),
                "status": ai_interpretation.get("status", "ok"),
                "latencyMs": ai_interpretation.get("latencyMs", 0),
                "warning": ai_interpretation.get("warning"),
            }
        else:
            skipped.append(AI_INTERPRETATION_SECTION)

    return data, skipped
