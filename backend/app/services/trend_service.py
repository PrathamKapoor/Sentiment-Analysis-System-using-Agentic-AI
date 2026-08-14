from collections import defaultdict
from datetime import timedelta

from app.models import Review, SentimentResult, AspectSentiment

GRANULARITIES = ("daily", "weekly", "monthly")


def _period_key(review_date, granularity):
    if granularity == "daily":
        return review_date.isoformat()
    if granularity == "weekly":
        monday = review_date - timedelta(days=review_date.weekday())
        return monday.isoformat()
    # monthly
    return f"{review_date.year:04d}-{review_date.month:02d}"


def get_trends(project_id, granularity="daily", filters=None):
    if granularity not in GRANULARITIES:
        granularity = "daily"
    filters = filters or {}

    query = (
        SentimentResult.query.join(Review, SentimentResult.review_id == Review.id)
        .filter(Review.project_id == project_id, Review.deleted_at.is_(None))
    )
    if filters.get("dateFrom"):
        query = query.filter(Review.review_date >= filters["dateFrom"])
    if filters.get("dateTo"):
        query = query.filter(Review.review_date <= filters["dateTo"])
    if filters.get("sourceId"):
        query = query.filter(Review.data_source_id == filters["sourceId"])
    if filters.get("datasetId"):
        query = query.filter(Review.dataset_id == filters["datasetId"])
    if filters.get("rating") is not None:
        query = query.filter(Review.rating == filters["rating"])
    if filters.get("aspectId"):
        aspect_review_ids = [
            row.review_id for row in
            AspectSentiment.query.filter_by(aspect_id=filters["aspectId"]).with_entities(AspectSentiment.review_id)
        ]
        query = query.filter(Review.id.in_(aspect_review_ids))

    results = query.all()

    buckets = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "confidence_sum": 0.0})
    skipped_no_date = 0
    for result in results:
        review_date = result.review.review_date
        if review_date is None:
            skipped_no_date += 1
            continue
        key = _period_key(review_date, granularity)
        bucket = buckets[key]
        bucket[result.sentiment_label] += 1
        bucket["confidence_sum"] += float(result.confidence_score)

    periods = []
    for period, bucket in sorted(buckets.items()):
        total = bucket["positive"] + bucket["negative"] + bucket["neutral"]
        periods.append({
            "period": period,
            "totalReviews": total,
            "positiveCount": bucket["positive"],
            "negativeCount": bucket["negative"],
            "neutralCount": bucket["neutral"],
            "positivePercentage": round(bucket["positive"] / total * 100, 2) if total else 0.0,
            "negativePercentage": round(bucket["negative"] / total * 100, 2) if total else 0.0,
            "neutralPercentage": round(bucket["neutral"] / total * 100, 2) if total else 0.0,
            "averageConfidence": round(bucket["confidence_sum"] / total, 4) if total else 0.0,
        })

    return {"granularity": granularity, "periods": periods, "skippedNoDate": skipped_no_date}
