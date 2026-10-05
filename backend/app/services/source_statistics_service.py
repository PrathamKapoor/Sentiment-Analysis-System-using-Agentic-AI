"""Actual per-origin source composition and evidence counts."""
from collections import Counter, defaultdict
from urllib.parse import urlsplit, urlunsplit

from app.models import DataSource, Dataset, Review, ReviewDuplicateLink, SecurityFinding, SentimentResult
from app.services.evidence_service import eligible_evidence_query
from app.services.feedback_intelligence_service import classify_feedback


def get_source_statistics(project_id):
    reviews = eligible_evidence_query(project_id).order_by(Review.created_at.asc()).all()
    groups = defaultdict(list)
    for review in reviews:
        key = ("data_source", str(review.data_source_id)) if review.data_source_id else ("dataset", str(review.dataset_id))
        groups[key].append(review)
    source_rows = {}
    for source in DataSource.query.filter_by(project_id=project_id).all():
        source_rows[("data_source", str(source.id))] = {"sourceId": str(source.id), "source": source.type,
            "sourceType": source.type, "url": _safe_url(source.url), "biasNote": _bias_note(source.type)}
    for dataset in Dataset.query.filter_by(project_id=project_id).all():
        source_rows[("dataset", str(dataset.id))] = {"sourceId": str(dataset.id), "source": "imported",
            "sourceType": "imported", "url": None, "biasNote": "User-provided dataset; sampling process is not independently verified."}

    findings_by_review = Counter(str(row.review_id) for row in SecurityFinding.query.filter_by(project_id=project_id).filter(
        SecurityFinding.status != "stale").all())
    items = []
    for key, meta in source_rows.items():
        records = groups.get(key, [])
        sentiment = Counter()
        categories = Counter()
        finding_count = 0
        dates = []
        for review in records:
            if review.review_date:
                dates.append(review.review_date.isoformat())
            if review.sentiment_result:
                sentiment[review.sentiment_result.sentiment_label] += 1
            for category in classify_feedback(review.text or ""):
                if category["category"] != "OTHER":
                    categories[category["category"]] += 1
            finding_count += findings_by_review[str(review.id)]
        ids = {str(row.id) for row in records}
        links = ReviewDuplicateLink.query.filter_by(project_id=project_id).filter(
            (ReviewDuplicateLink.review_id.in_(ids) if ids else False) |
            (ReviewDuplicateLink.duplicate_review_id.in_(ids) if ids else False)
        ).count()
        items.append({**meta, "recordCount": len(records), "canonicalEvidenceCount": max(len(records) - links, 0),
            "duplicateCount": links, "dateRange": {"from": min(dates) if dates else None, "to": max(dates) if dates else None},
            "sentimentDistribution": dict(sentiment), "feedbackCategoryDistribution": dict(categories),
            "securityFindingCount": finding_count})
    visible_ids = {str(row.id) for row in reviews}
    links = [link for link in ReviewDuplicateLink.query.filter_by(project_id=project_id).all()
             if str(link.review_id) in visible_ids and str(link.duplicate_review_id) in visible_ids]
    parent = {str(row.id): str(row.id) for row in reviews}

    def find(value):
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for link in links:
        left, right = find(str(link.review_id)), find(str(link.duplicate_review_id))
        if left != right:
            parent[right] = left
    canonical_ids = {find(str(row.id)) for row in reviews}
    duplicate_ids = {str(link.duplicate_review_id) for link in links}
    for item in items:
        source_ids = {str(review.id) for review in groups.get(("data_source" if item["sourceType"] != "imported" else "dataset", item["sourceId"]), [])}
        item["canonicalEvidenceCount"] = sum(1 for review_id in source_ids if find(review_id) == review_id)
        item["duplicateCount"] = len(source_ids & duplicate_ids)
    return {"recordCount": len(reviews), "canonicalEvidenceCount": len(canonical_ids),
            "duplicateRelationshipCount": len(links), "sources": items,
            "limitations": ["Counts exclude deleted, spam, and legacy-flagged duplicate reviews.",
                            "Source counts describe records, not unique customers.",
                            "Feedback category counts use the configured deterministic phrase rules."]}


def _bias_note(source_type):
    return {"amazon": "Consumer marketplace reviews; self-selected reviewers.",
            "flipkart": "Consumer marketplace reviews; self-selected reviewers.",
            "reddit": "Discussion/community content; not a representative customer sample.",
            "github_issues": "Technical issue reports; not a representative consumer review sample."}.get(
                (source_type or "").lower(), "Source-specific sampling bias is not characterized.")


def _safe_url(value):
    try:
        parts = urlsplit(value or "")
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path[:1024], "", ""))
    except (ValueError, UnicodeError):
        return None
