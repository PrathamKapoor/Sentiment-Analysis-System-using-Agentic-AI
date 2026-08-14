"""AI Summary generation — deterministic templates over stored analytical
data, not an LLM. Works fully without one; see the module docstring pattern
already established in topic_service.py/recommendation_service.py.

Every number in a generated summary traces directly back to a service call
against already-stored data (sentiment_service, topic_service,
keyword_service, aspect_service, recommendation_service, trend_service) —
nothing is invented. Summaries state facts ("X% of reviews were negative")
and, at most, name the most-frequent contributing factor ("delivery was the
most common negative aspect") — never a causal claim ("sales dropped
because..."). All output is clearly system/AI-generated and requires human
approval before being treated as final (see ai-summaries approval workflow).
"""
from app.services import sentiment_service, topic_service, keyword_service, aspect_service, recommendation_service, trend_service

SUMMARY_TYPES = ("overall", "executive", "positive", "negative", "comparative", "periodic")
GENERATION_METHOD = "deterministic_template"


def gather_analytics(project_id, date_from=None, date_to=None):
    filters = {"dateFrom": date_from, "dateTo": date_to}
    sentiment = sentiment_service.get_summary(project_id, filters)
    topics = topic_service.list_topics(project_id)
    keywords = keyword_service.extract_keywords(project_id, filters=filters, top_n=5)
    aspects = aspect_service.list_aspects(project_id, filters)
    recommendations = recommendation_service.list_recommendations(project_id, {"status": "new"})
    trend = trend_service.get_trends(project_id, "monthly", filters)

    positive_aspects = sorted(
        [a for a in aspects if a["positiveCount"] > 0], key=lambda a: a["positivePercentage"], reverse=True
    )
    negative_aspects = sorted(
        [a for a in aspects if a["negativeCount"] > 0], key=lambda a: a["negativePercentage"], reverse=True
    )

    return {
        "sentiment": sentiment,
        "topTopics": topics[:3],
        "topKeywords": [k["keyword"] for k in keywords],
        "topPositiveAspects": positive_aspects[:3],
        "topNegativeAspects": negative_aspects[:3],
        "openRecommendations": recommendations,
        "trendPeriods": trend["periods"],
    }


def _trend_direction(periods):
    if len(periods) < 2:
        return None
    prev, latest = periods[-2], periods[-1]
    if latest["negativePercentage"] > prev["negativePercentage"]:
        return "increasing"
    if latest["negativePercentage"] < prev["negativePercentage"]:
        return "decreasing"
    return "stable"


def _fact_sentence(analytics):
    s = analytics["sentiment"]
    if s["analysedReviews"] == 0:
        return "No analysed reviews are available for this date range yet."
    return (
        f"Of {s['analysedReviews']} analysed reviews, {s['positive']['percentage']}% were positive, "
        f"{s['negative']['percentage']}% negative and {s['neutral']['percentage']}% neutral "
        f"(average confidence {round(s['averageConfidence'] * 100, 1)}%)."
    )


def _aspect_sentence(analytics):
    parts = []
    if analytics["topNegativeAspects"]:
        top_neg = analytics["topNegativeAspects"][0]
        parts.append(
            f"\"{top_neg['name']}\" is the most frequently identified negative aspect in the analysed feedback "
            f"({top_neg['negativePercentage']}% negative across {top_neg['frequency']} mentions)."
        )
    if analytics["topPositiveAspects"]:
        top_pos = analytics["topPositiveAspects"][0]
        parts.append(
            f"\"{top_pos['name']}\" is the most frequently identified positive aspect "
            f"({top_pos['positivePercentage']}% positive across {top_pos['frequency']} mentions)."
        )
    return " ".join(parts) if parts else "No aspect-level data is available for this date range yet."


def _topic_sentence(analytics):
    if not analytics["topTopics"]:
        return "No topic analysis data is available for this date range yet."
    names = ", ".join(f"\"{t['topicName']}\"" for t in analytics["topTopics"])
    return f"The most prominent topics identified in the feedback are {names}."


def _keyword_sentence(analytics):
    if not analytics["topKeywords"]:
        return ""
    return f"Frequently mentioned terms include {', '.join(analytics['topKeywords'])}."


def _recommendation_sentence(analytics):
    count = len(analytics["openRecommendations"])
    if count == 0:
        return "No open recommendations have been generated for this project."
    return f"{count} system-generated recommendation(s) are currently open and awaiting review."


def generate_sentiment_summary(analytics):
    return " ".join(filter(None, [_fact_sentence(analytics)]))


def generate_executive_summary(analytics):
    direction = _trend_direction(analytics["trendPeriods"])
    trend_note = f" The negative-sentiment share has been {direction} over the most recent periods." if direction else ""
    return " ".join(filter(None, [
        _fact_sentence(analytics), _aspect_sentence(analytics), trend_note.strip(),
        _recommendation_sentence(analytics),
    ]))


def generate_positive_summary(analytics):
    if not analytics["topPositiveAspects"]:
        return "No aspect-level positive-sentiment data is available for this date range yet."
    lines = [
        f"\"{a['name']}\" — {a['positivePercentage']}% positive across {a['frequency']} mentions"
        for a in analytics["topPositiveAspects"]
    ]
    return "Aspects with the strongest positive sentiment: " + "; ".join(lines) + "."


def generate_negative_summary(analytics):
    if not analytics["topNegativeAspects"]:
        return "No aspect-level negative-sentiment data is available for this date range yet."
    lines = [
        f"\"{a['name']}\" — {a['negativePercentage']}% negative across {a['frequency']} mentions"
        for a in analytics["topNegativeAspects"]
    ]
    return "Aspects with the strongest negative sentiment: " + "; ".join(lines) + f". {_recommendation_sentence(analytics)}"


def generate_comparative_summary(analytics):
    direction = _trend_direction(analytics["trendPeriods"])
    if direction is None:
        return "Not enough historical data across periods to generate a period-over-period comparison yet."
    return (
        f"Negative-sentiment share is {direction} compared to the previous period in this date range. "
        f"{_fact_sentence(analytics)}"
    )


def generate_periodic_summary(analytics, date_from, date_to):
    return f"For the period {date_from} to {date_to}: {_fact_sentence(analytics)} {_topic_sentence(analytics)}"


def generate_overall_summary(analytics):
    return " ".join(filter(None, [
        _fact_sentence(analytics), _topic_sentence(analytics), _aspect_sentence(analytics),
        _keyword_sentence(analytics),
    ]))


_GENERATORS = {
    "overall": lambda a, df, dt: generate_overall_summary(a),
    "executive": lambda a, df, dt: generate_executive_summary(a),
    "positive": lambda a, df, dt: generate_positive_summary(a),
    "negative": lambda a, df, dt: generate_negative_summary(a),
    "comparative": lambda a, df, dt: generate_comparative_summary(a),
    "periodic": lambda a, df, dt: generate_periodic_summary(a, df, dt),
}


def generate_project_summary(project_id, summary_type, date_from, date_to, actor_user_id):
    analytics = gather_analytics(project_id, date_from, date_to)
    generator = _GENERATORS.get(summary_type, _GENERATORS["overall"])
    text = generator(analytics, date_from, date_to)

    return {
        "summaryType": summary_type,
        "generationMethod": GENERATION_METHOD,
        "generatedByUserId": str(actor_user_id),
        "sections": {
            "overall": text,
            "sentiment": _fact_sentence(analytics),
            "topics": _topic_sentence(analytics),
            "aspects": _aspect_sentence(analytics),
            "keywords": _keyword_sentence(analytics),
            "recommendations": _recommendation_sentence(analytics),
        },
    }
