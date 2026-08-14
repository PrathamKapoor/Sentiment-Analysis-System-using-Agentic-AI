"""Product/Brand Comparison — computed dynamically from existing analysis
data (reviews, sentiment_results, aspects, aspect_sentiments, topics,
keywords). No comparison-results table: nothing here is persisted, it's
recomputed on every request from already-stored analysis.

Comparison entities are projects within the caller's own organisation — per
the already-approved REST API Spec's documented `targetProjectIds` body
shape, and because the data model scopes everything by project, not by an
arbitrary "brand" string. Cross-organisation comparison is rejected outright.
"""
from app.errors.exceptions import ValidationError, NotFoundError
from app.models import Project, Review, SentimentResult, AspectSentiment
from app.services import keyword_service, trend_service


def _project_metrics(project, date_from=None, date_to=None):
    reviews_query = Review.query.filter_by(project_id=project.id).filter(Review.deleted_at.is_(None))
    if date_from:
        reviews_query = reviews_query.filter(Review.review_date >= date_from)
    if date_to:
        reviews_query = reviews_query.filter(Review.review_date <= date_to)
    reviews = reviews_query.all()
    total_reviews = len(reviews)

    review_ids = [r.id for r in reviews]
    results = (
        SentimentResult.query.filter(SentimentResult.review_id.in_(review_ids)).all()
        if review_ids else []
    )
    analysed = len(results)
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    confidence_sum = 0.0
    for r in results:
        counts[r.sentiment_label] += 1
        confidence_sum += float(r.confidence_score)

    def pct(n):
        return round((n / analysed) * 100, 2) if analysed else None

    ratings = [float(r.rating) for r in reviews if r.rating is not None]
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

    # Top positive/negative aspect by count of that sentiment label among this project's aspect_sentiments.
    aspect_links = (
        AspectSentiment.query.join(Review, AspectSentiment.review_id == Review.id)
        .filter(Review.project_id == project.id, Review.deleted_at.is_(None)).all()
    )
    aspect_counts = {}  # aspect_name -> {label: count}
    for link in aspect_links:
        name = link.aspect.name
        aspect_counts.setdefault(name, {"positive": 0, "negative": 0, "neutral": 0})
        aspect_counts[name][link.sentiment_label] += 1

    top_positive_aspect = max(
        (a for a in aspect_counts.items() if a[1]["positive"] > 0),
        key=lambda a: a[1]["positive"], default=None,
    )
    top_negative_aspect = max(
        (a for a in aspect_counts.items() if a[1]["negative"] > 0),
        key=lambda a: a[1]["negative"], default=None,
    )

    top_keywords = keyword_service.extract_keywords(project.id, top_n=5)
    trends = trend_service.get_trends(project.id, "monthly", {"dateFrom": date_from, "dateTo": date_to})

    return {
        "projectId": str(project.id),
        "name": project.name,
        "totalReviews": total_reviews,
        "analysedReviews": analysed,
        "positiveCount": counts["positive"],
        "negativeCount": counts["negative"],
        "neutralCount": counts["neutral"],
        "positivePercentage": pct(counts["positive"]),
        "negativePercentage": pct(counts["negative"]),
        "neutralPercentage": pct(counts["neutral"]),
        "averageRating": average_rating,
        "averageConfidence": round(confidence_sum / analysed, 4) if analysed else None,
        "topPositiveAspect": top_positive_aspect[0] if top_positive_aspect else None,
        "topNegativeAspect": top_negative_aspect[0] if top_negative_aspect else None,
        "topKeywords": [k["keyword"] for k in top_keywords],
        "reviewVolume": total_reviews,
        "sentimentTrend": trends["periods"],
    }


def _narrative(entities):
    """Deterministic template narrative — observed data only, no causal claims."""
    if len(entities) < 2:
        return None
    with_positive = [e for e in entities if e["positivePercentage"] is not None]
    if not with_positive:
        return "Not enough analysed data across the selected projects to compare sentiment."

    best = max(with_positive, key=lambda e: e["positivePercentage"])
    lines = [f"{best['name']} has the highest positive sentiment percentage ({best['positivePercentage']}%)."]

    negative_aspects = [(e["name"], e["topNegativeAspect"]) for e in entities if e["topNegativeAspect"]]
    for name, aspect in negative_aspects:
        lines.append(f"{name}'s most common negative feedback relates to \"{aspect}\".")

    return " ".join(lines)


def compare_projects(organisation_id, target_project_ids, date_from=None, date_to=None):
    if len(target_project_ids) < 2:
        raise ValidationError("At least two target project IDs are required for comparison")

    projects = Project.query.filter(
        Project.id.in_(target_project_ids), Project.deleted_at.is_(None)
    ).all()
    found_ids = {str(p.id) for p in projects}
    missing = set(target_project_ids) - found_ids
    if missing:
        raise NotFoundError("One or more target projects were not found")

    cross_org = [p for p in projects if str(p.organisation_id) != str(organisation_id)]
    if cross_org:
        # Same 404-not-403 tenant-isolation rule used everywhere else in this API.
        raise NotFoundError("One or more target projects were not found")

    entities = [_project_metrics(p, date_from, date_to) for p in projects]
    return {
        "entities": entities,
        "narrative": _narrative(entities),
    }
