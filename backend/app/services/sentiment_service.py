from datetime import datetime, timezone

from app.extensions import db
from app.errors.exceptions import ValidationError, NotFoundError
from app.models import Review, SentimentResult, Project
from app.models.sentiment_result import LABELS
from app.services.sentiment_analyzer import get_analyzer
from app.services.audit_service import log_action

BATCH_SIZE = 100


def eligible_reviews_query(project_id, include_spam=False, include_duplicates=False):
    query = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))
    if not include_spam:
        query = query.filter(Review.is_spam.is_(False))
    if not include_duplicates:
        query = query.filter(Review.is_duplicate.is_(False))
    return query


def _has_usable_text(review):
    return bool(review.text and review.text.strip())


def run_analysis(project_id, actor_user_id, include_spam=False, include_duplicates=False, force=False):
    """Analyses eligible reviews without a sentiment_result (or all of them if
    force=True, for re-analysis). Runs in fixed-size batches, committing after
    each — keeps a single run from holding one giant open transaction.
    """
    organisation_id = db.session.get(Project, project_id).organisation_id

    log_action(organisation_id, actor_user_id, "sentiment_analysis.started", "project", project_id, {
        "force": force,
    })
    db.session.commit()

    query = eligible_reviews_query(project_id, include_spam, include_duplicates)
    if not force:
        query = query.outerjoin(SentimentResult).filter(SentimentResult.id.is_(None))
    reviews = query.all()

    analyzer = get_analyzer()
    analysed_count = 0
    skipped_empty_text = 0

    try:
        batch = []
        for review in reviews:
            if not _has_usable_text(review):
                skipped_empty_text += 1
                continue
            batch.append(review)
            if len(batch) >= BATCH_SIZE:
                analysed_count += _analyze_and_store(batch, analyzer)
                batch = []
        if batch:
            analysed_count += _analyze_and_store(batch, analyzer)

        log_action(organisation_id, actor_user_id, "sentiment_analysis.completed", "project", project_id, {
            "analysedCount": analysed_count, "skippedEmptyText": skipped_empty_text,
        })
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log_action(
            organisation_id, actor_user_id, "sentiment_analysis.failed", "project", project_id,
            {"error": str(exc)},
        )
        db.session.commit()
        raise

    return {
        "eligibleReviews": len(reviews),
        "analysedCount": analysed_count,
        "skippedEmptyText": skipped_empty_text,
    }


def _analyze_and_store(reviews, analyzer):
    texts = [r.text for r in reviews]
    results = analyzer.analyze_batch(texts)
    count = 0
    for review, result in zip(reviews, results):
        existing = SentimentResult.query.filter_by(review_id=review.id).first()
        if existing:
            existing.sentiment_label = result["label"]
            existing.positive_score = result["positive_score"]
            existing.negative_score = result["negative_score"]
            existing.neutral_score = result["neutral_score"]
            existing.confidence_score = result["confidence_score"]
            existing.compound_score = result.get("compound")
            existing.vader_breakdown = result.get("vader_breakdown")
            existing.model_name = result["model_name"]
            existing.model_version = result["model_version"]
            existing.analysed_at = datetime.now(timezone.utc)
            # Re-analysis with the automated model clears any prior manual
            # correction marker — it's a fresh automated result now.
            existing.corrected_by_user_id = None
            existing.corrected_at = None
        else:
            db.session.add(SentimentResult(
                review_id=review.id,
                sentiment_label=result["label"],
                positive_score=result["positive_score"],
                negative_score=result["negative_score"],
                neutral_score=result["neutral_score"],
                confidence_score=result["confidence_score"],
                compound_score=result.get("compound"),
                vader_breakdown=result.get("vader_breakdown"),
                model_name=result["model_name"],
                model_version=result["model_version"],
            ))
        count += 1
    db.session.flush()
    return count


def get_summary(project_id, filters=None):
    reviews_query = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))
    total_reviews = reviews_query.count()

    results_query = (
        SentimentResult.query.join(Review, SentimentResult.review_id == Review.id)
        .filter(Review.project_id == project_id, Review.deleted_at.is_(None))
    )
    results_query = _apply_result_filters(results_query, filters or {})
    results = results_query.all()

    analysed = len(results)
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    confidence_sum = 0.0
    for r in results:
        counts[r.sentiment_label] += 1
        confidence_sum += float(r.confidence_score)

    def pct(n):
        return round((n / analysed) * 100, 2) if analysed else 0.0

    return {
        "totalReviews": total_reviews,
        "analysedReviews": analysed,
        "positive": {"count": counts["positive"], "percentage": pct(counts["positive"])},
        "negative": {"count": counts["negative"], "percentage": pct(counts["negative"])},
        "neutral": {"count": counts["neutral"], "percentage": pct(counts["neutral"])},
        "averageConfidence": round(confidence_sum / analysed, 4) if analysed else 0.0,
        "model": {"name": "vader", "version": "3.3.2"} if analysed else None,
    }


def _apply_result_filters(query, filters):
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
    if filters.get("sentiment"):
        query = query.filter(SentimentResult.sentiment_label == filters["sentiment"])
    if filters.get("minimumConfidence") is not None:
        query = query.filter(SentimentResult.confidence_score >= filters["minimumConfidence"])
    # NOTE: 'language' is accepted (per the Phase 3 filter list) but not
    # applied — reviews has no language column in the approved schema.
    return query


def list_results(project_id, filters=None, limit=None):
    query = (
        SentimentResult.query.join(Review, SentimentResult.review_id == Review.id)
        .filter(Review.project_id == project_id, Review.deleted_at.is_(None))
    )
    query = _apply_result_filters(query, filters or {})
    query = query.order_by(SentimentResult.analysed_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_review_sentiment(review):
    if review.sentiment_result is None:
        raise NotFoundError("This review has not been analysed yet")
    return review.sentiment_result


def correct_sentiment(review, corrected_label, corrected_by_user_id, reason=None):
    if corrected_label not in LABELS:
        raise ValidationError(f"label must be one of: {', '.join(LABELS)}")

    now = datetime.now(timezone.utc)
    result = review.sentiment_result
    if result is None:
        # No automated result exists yet — a human-only judgement call.
        # Winning label gets 1.0, others 0.0; confidence is definitionally 1.0
        # since this is a direct human assertion, not a model estimate.
        scores = {label: 0.0 for label in LABELS}
        scores[corrected_label] = 1.0
        result = SentimentResult(
            review_id=review.id,
            sentiment_label=corrected_label,
            positive_score=scores["positive"],
            negative_score=scores["negative"],
            neutral_score=scores["neutral"],
            confidence_score=1.0,
            compound_score=None,
            vader_breakdown=None,
            model_name="manual",
            model_version="n/a",
            analysed_at=now,
        )
        db.session.add(result)
    else:
        result.sentiment_label = corrected_label
        # A manual correction overrides the VADER explanation — the existing
        # breakdown was for the automated label, not the human one.
        result.vader_breakdown = None
        result.compound_score = None

    result.corrected_by_user_id = corrected_by_user_id
    result.corrected_at = now
    db.session.flush()

    # Correction history lives in audit_logs — the approved schema doesn't
    # have a separate correction-reason column, and adding one wasn't
    # justified the way relevance_score was (corrected_by/corrected_at
    # already capture "who and when"; audit_logs captures "why").
    log_action(
        review.project.organisation_id, corrected_by_user_id, "sentiment.corrected",
        "sentiment_result", result.id,
        {"reviewId": str(review.id), "correctedLabel": corrected_label, "reason": reason},
    )
    return result
