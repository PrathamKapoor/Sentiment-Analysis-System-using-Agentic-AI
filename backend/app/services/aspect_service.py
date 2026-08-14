from app.extensions import db
from app.errors.exceptions import ValidationError
from app.models import Aspect, AspectSentiment, Review, Project
from app.services.sentiment_service import eligible_reviews_query
from app.services.aspect_analyzer import get_aspect_analyzer
from app.services.audit_service import log_action

BATCH_SIZE = 100


def _get_or_create_aspect(project_id, name, cache):
    if name in cache:
        return cache[name]
    aspect = Aspect.query.filter_by(project_id=project_id, name=name).first()
    if aspect is None:
        aspect = Aspect(project_id=project_id, name=name)
        db.session.add(aspect)
        db.session.flush()
    cache[name] = aspect
    return aspect


def run_aspect_analysis(project_id, actor_user_id, include_spam=False, include_duplicates=False, force=False):
    organisation_id = db.session.get(Project, project_id).organisation_id
    log_action(organisation_id, actor_user_id, "aspect_analysis.started", "project", project_id, {"force": force})
    db.session.commit()

    query = eligible_reviews_query(project_id, include_spam, include_duplicates)
    if not force:
        query = query.outerjoin(AspectSentiment, AspectSentiment.review_id == Review.id).filter(
            AspectSentiment.id.is_(None)
        )
    reviews = query.all()

    analyzer = get_aspect_analyzer()
    aspect_cache = {}
    analysed_review_count = 0
    aspect_link_count = 0

    try:
        for review in reviews:
            if not review.text or not review.text.strip():
                continue
            results = analyzer.analyse_review(review.text)
            for result in results:
                aspect = _get_or_create_aspect(project_id, result["aspect"], aspect_cache)
                existing = AspectSentiment.query.filter_by(review_id=review.id, aspect_id=aspect.id).first()
                if existing:
                    existing.sentiment_label = result["label"]
                    existing.confidence_score = result["confidence_score"]
                else:
                    db.session.add(AspectSentiment(
                        review_id=review.id,
                        aspect_id=aspect.id,
                        sentiment_label=result["label"],
                        confidence_score=result["confidence_score"],
                    ))
                aspect_link_count += 1
            analysed_review_count += 1
            if analysed_review_count % BATCH_SIZE == 0:
                db.session.flush()

        log_action(organisation_id, actor_user_id, "aspect_analysis.completed", "project", project_id, {
            "reviewsAnalysed": analysed_review_count, "aspectLinksCreated": aspect_link_count,
        })
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log_action(organisation_id, actor_user_id, "aspect_analysis.failed", "project", project_id, {"error": str(exc)})
        db.session.commit()
        raise

    return {"eligibleReviews": len(reviews), "reviewsAnalysed": analysed_review_count, "aspectLinksCreated": aspect_link_count}


def _apply_aspect_sentiment_filters(query, filters):
    if filters.get("dateFrom"):
        query = query.filter(Review.review_date >= filters["dateFrom"])
    if filters.get("dateTo"):
        query = query.filter(Review.review_date <= filters["dateTo"])
    if filters.get("sourceId"):
        query = query.filter(Review.data_source_id == filters["sourceId"])
    if filters.get("datasetId"):
        query = query.filter(Review.dataset_id == filters["datasetId"])
    if filters.get("sentiment"):
        query = query.filter(AspectSentiment.sentiment_label == filters["sentiment"])
    if filters.get("minimumConfidence") is not None:
        query = query.filter(AspectSentiment.confidence_score >= filters["minimumConfidence"])
    return query


def _aspect_stats(aspect, filters):
    query = (
        AspectSentiment.query.join(Review, AspectSentiment.review_id == Review.id)
        .filter(AspectSentiment.aspect_id == aspect.id, Review.deleted_at.is_(None))
    )
    query = _apply_aspect_sentiment_filters(query, filters)
    links = query.all()

    counts = {"positive": 0, "negative": 0, "neutral": 0}
    confidence_sum = 0.0
    for link in links:
        counts[link.sentiment_label] += 1
        confidence_sum += float(link.confidence_score)

    total = len(links)

    def pct(n):
        return round((n / total) * 100, 2) if total else 0.0

    return {
        **aspect.to_dict(frequency=total),
        "positiveCount": counts["positive"],
        "negativeCount": counts["negative"],
        "neutralCount": counts["neutral"],
        "positivePercentage": pct(counts["positive"]),
        "negativePercentage": pct(counts["negative"]),
        "neutralPercentage": pct(counts["neutral"]),
        "averageConfidence": round(confidence_sum / total, 4) if total else 0.0,
    }


def list_aspects(project_id, filters=None, minimum_frequency=None):
    filters = filters or {}
    aspects = Aspect.query.filter_by(project_id=project_id).order_by(Aspect.name).all()
    result = [_aspect_stats(a, filters) for a in aspects]
    if minimum_frequency:
        result = [r for r in result if r["frequency"] >= minimum_frequency]
    result.sort(key=lambda r: r["frequency"], reverse=True)
    return result


def get_aspect_detail(aspect, filters=None):
    return _aspect_stats(aspect, filters or {})


def list_aspect_reviews(aspect, filters=None):
    query = (
        AspectSentiment.query.join(Review, AspectSentiment.review_id == Review.id)
        .filter(AspectSentiment.aspect_id == aspect.id, Review.deleted_at.is_(None))
    )
    query = _apply_aspect_sentiment_filters(query, filters or {})
    links = query.all()

    analyzer = get_aspect_analyzer()
    results = []
    for link in links:
        review = link.review
        evidence = analyzer.local_context(review.text, aspect.name)
        body = review.to_dict()
        body["aspectSentiment"] = link.to_dict(evidence_text=evidence)
        results.append(body)
    return results


def list_review_aspects(review):
    analyzer = get_aspect_analyzer()
    links = AspectSentiment.query.filter_by(review_id=review.id).all()
    result = []
    for link in links:
        evidence = analyzer.local_context(review.text, link.aspect.name)
        result.append(link.to_dict(evidence_text=evidence))
    return result
