"""Project-scoped access to canonical evidence (the existing Review rows)."""
from uuid import UUID

from app.errors.exceptions import NotFoundError
from app.models import DataSource, Dataset, Review


def eligible_evidence_query(project_id, *, include_spam=False, include_duplicates=False, include_deleted=False):
    query = Review.query.filter(Review.project_id == project_id)
    if not include_deleted:
        query = query.filter(Review.deleted_at.is_(None))
    if not include_spam:
        query = query.filter(Review.is_spam.is_(False))
    if not include_duplicates:
        query = query.filter(Review.is_duplicate.is_(False))
    return query


def serialize_evidence(review):
    source = DataSource.query.filter_by(id=review.data_source_id, project_id=review.project_id).first() if review.data_source_id else None
    dataset = Dataset.query.filter_by(id=review.dataset_id, project_id=review.project_id).first() if review.dataset_id else None
    return {
        "evidenceId": str(review.id), "reviewId": str(review.id), "projectId": str(review.project_id),
        "source": review.source, "sourceType": source.type if source else ("imported" if dataset else "unknown"),
        "sourceId": str(source.id) if source else None, "datasetId": str(dataset.id) if dataset else None,
        "provider": source.type if source else ("imported" if dataset else None),
        "providerRecordId": review.source_record_id,
        "canonicalUrl": review.source_url,
        "observedAt": review.review_date.isoformat() if review.review_date else None,
        "collectedAt": review.source_collected_at.isoformat() if review.source_collected_at else None,
        "content": review.text, "contentType": "review", "provenance": review.source_metadata or {},
    }


def get_evidence(project_id, review_id, *, include_spam=False, include_duplicates=False):
    try:
        review_id = UUID(str(review_id))
    except (ValueError, TypeError, AttributeError):
        raise NotFoundError("Evidence not found")
    review = eligible_evidence_query(project_id, include_spam=include_spam,
                                     include_duplicates=include_duplicates).filter_by(id=review_id).first()
    if review is None:
        raise NotFoundError("Evidence not found")
    return serialize_evidence(review)
