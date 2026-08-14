from datetime import datetime, timezone

from app.extensions import db
from app.models import Review, SentimentResult


def list_reviews(project_id, filters):
    query = Review.query.filter_by(project_id=project_id).filter(Review.deleted_at.is_(None))

    if filters.get("source"):
        query = query.filter(Review.source == filters["source"])
    if filters.get("rating") is not None:
        query = query.filter(Review.rating == filters["rating"])
    if filters.get("dateFrom"):
        query = query.filter(Review.review_date >= filters["dateFrom"])
    if filters.get("dateTo"):
        query = query.filter(Review.review_date <= filters["dateTo"])
    if filters.get("search"):
        query = query.filter(Review.text.ilike(f"%{filters['search']}%"))
    if filters.get("sentiment"):
        query = query.join(SentimentResult).filter(SentimentResult.sentiment_label == filters["sentiment"])

    return query.order_by(Review.created_at.desc()).all()


def update_review(review, data):
    for field, attr in [
        ("text", "text"), ("rating", "rating"), ("reviewDate", "review_date"),
        ("source", "source"), ("isSpam", "is_spam"), ("isDuplicate", "is_duplicate"),
    ]:
        if field in data:
            setattr(review, attr, data[field])
    db.session.commit()
    return review


def mark_spam(review, is_spam=True):
    review.is_spam = is_spam
    db.session.commit()
    return review


def soft_delete_review(review):
    review.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
