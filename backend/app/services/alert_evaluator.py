"""AlertEvaluator — computes a single current metric value from already-
stored analytics and compares it against a rule's threshold. Manual/on-demand
only in Phase 5 (via POST .../evaluate) — no scheduled background monitoring.
"""
from datetime import date, timedelta

from app.models import Review
from app.services import sentiment_service, keyword_service, aspect_service, recommendation_service

OPERATORS = {
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
    "==": lambda v, t: v == t,
}


def _window_date_from(window_days):
    if not window_days:
        return None
    return date.today() - timedelta(days=window_days)


def compute_metric(project_id, rule_condition):
    metric = rule_condition.get("metric")
    window_days = rule_condition.get("timeWindowDays")
    date_from = _window_date_from(window_days)
    filters = {"dateFrom": date_from} if date_from else {}

    if metric == "negative_sentiment_percentage":
        return sentiment_service.get_summary(project_id, filters)["negative"]["percentage"]

    if metric == "negative_review_count":
        return sentiment_service.get_summary(project_id, filters)["negative"]["count"]

    if metric == "average_rating":
        query = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))
        if date_from:
            query = query.filter(Review.review_date >= date_from)
        ratings = [float(r.rating) for r in query.all() if r.rating is not None]
        return round(sum(ratings) / len(ratings), 2) if ratings else None

    if metric == "keyword_frequency":
        keyword = rule_condition.get("keyword")
        if not keyword:
            return 0
        results = keyword_service.extract_keywords(project_id, filters=filters, top_n=1000, search=keyword)
        match = next((k for k in results if k["keyword"] == keyword.lower()), None)
        return match["frequency"] if match else 0

    if metric == "aspect_negativity_percentage":
        aspect_name = rule_condition.get("aspectName")
        aspects = aspect_service.list_aspects(project_id, filters)
        match = next((a for a in aspects if a["name"] == aspect_name), None)
        return match["negativePercentage"] if match else None

    if metric == "review_volume":
        query = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))
        if date_from:
            query = query.filter(Review.review_date >= date_from)
        return query.count()

    if metric == "recommendation_priority":
        open_recs = recommendation_service.list_recommendations(project_id, {"status": "new", "priority": "high"})
        return len(open_recs)

    return None


def evaluate(project_id, rule_condition):
    metric = rule_condition.get("metric")
    operator = rule_condition.get("operator")
    threshold = rule_condition.get("threshold")

    if metric is None or operator not in OPERATORS or threshold is None:
        return {"triggered": False, "currentValue": None, "message": "Rule is not fully configured."}

    current_value = compute_metric(project_id, rule_condition)
    if current_value is None:
        return {
            "triggered": False, "currentValue": None,
            "message": f"Not enough data to evaluate '{metric}' yet.",
        }

    triggered = OPERATORS[operator](current_value, threshold)
    message = (
        f"{metric} is {current_value} ({operator} threshold {threshold})"
        if triggered else
        f"{metric} is {current_value}, within threshold ({operator} {threshold} not met)"
    )
    return {"triggered": triggered, "currentValue": current_value, "message": message}
