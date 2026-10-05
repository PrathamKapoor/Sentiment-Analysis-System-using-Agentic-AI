"""Conservative exact-duplicate linking; source rows are never mutated or removed."""
import hashlib
from urllib.parse import urlsplit, urlunsplit

from app.extensions import db
from app.models import Review, ReviewDuplicateLink
from app.services.text_cleaning import normalize_for_dedup


def _canonical_url(value):
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        host = parts.hostname.lower()
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), "", ""))
    except (ValueError, TypeError):
        return None


def _fingerprint(review):
    # Full normalized body equality is an exact signal; no short/common text is linked.
    text = normalize_for_dedup(review.text or "")
    if len(text) < 24:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_project_duplicates(project_id, *, limit=5000):
    reviews = Review.query.filter_by(project_id=project_id).filter(
        Review.deleted_at.is_(None), Review.is_spam.is_(False), Review.is_duplicate.is_(False)
    ).order_by(Review.created_at.asc(), Review.id.asc()).limit(min(max(int(limit), 1), 10000)).all()
    by_provider = {}
    by_url = {}
    by_content = {}
    candidates = []
    for item in reviews:
        keys = []
        if item.source_record_id and item.data_source_id:
            provider = (item.source or "").strip().casefold()
            # Provider record IDs are scoped by configured collection source
            # unless an adapter has a separately verified global ID contract.
            keys.append(("PROVIDER_ID", f"{provider}:{item.data_source_id}:{item.source_record_id}"))
        canonical_url = _canonical_url(item.source_url)
        if canonical_url:
            keys.append(("CANONICAL_URL", canonical_url))
        digest = _fingerprint(item)
        if digest:
            keys.append(("NORMALIZED_CONTENT_SHA256", digest))
        for method, key in keys:
            index = {"PROVIDER_ID": by_provider, "CANONICAL_URL": by_url,
                     "NORMALIZED_CONTENT_SHA256": by_content}[method]
            previous = index.get(key)
            if previous is not None and previous.id != item.id:
                if previous.data_source_id != item.data_source_id or method != "PROVIDER_ID":
                    candidates.append((previous, item, method))
            else:
                index[key] = item

    existing = set()
    for row in ReviewDuplicateLink.query.filter_by(project_id=project_id).all():
        left, right = str(row.review_id), str(row.duplicate_review_id)
        existing.add((left, right))
        existing.add((right, left))
    created = 0
    for first, second, method in candidates:
        # The ordered scan makes the first observed record the group anchor.
        left, right = str(first.id), str(second.id)
        pair = (left, right)
        if pair in existing:
            continue
        # At present only fully exact identities/text are automatically linked.
        row = ReviewDuplicateLink(project_id=project_id, review_id=left,
                                  duplicate_review_id=right,
                                  relationship_type="EXACT_DUPLICATE", strength=1.0,
                                  method=method)
        db.session.add(row)
        existing.add(pair)
        existing.add((right, left))
        created += 1
    db.session.flush()
    rows = ReviewDuplicateLink.query.filter_by(project_id=project_id).order_by(ReviewDuplicateLink.created_at.desc()).limit(1000).all()
    return {"created": created, "items": [row.to_dict() for row in rows], "scanned": len(reviews),
            "truncated": len(reviews) >= min(max(int(limit), 1), 10000),
            "limitations": ["Only exact provider identity, canonical URL, or normalized full-text equality creates a relationship.",
                            "Source records remain unchanged and independently traceable."]}
