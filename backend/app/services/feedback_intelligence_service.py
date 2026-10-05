"""Deterministic, evidence-linked feedback categories for stored project reviews."""
import re

from app.models import ProjectEntity, Review
from app.services.security_intelligence_service import extract_security_signals


_CATEGORY_RULES = (
    ("PRAISE", re.compile(r"\b(?:love|excellent|great|amazing|fantastic|works perfectly|highly recommend)\b", re.I)),
    ("COMPLAINT", re.compile(r"\b(?:disappointed|terrible|awful|does not work|doesn't work|poor quality|very bad)\b", re.I)),
    ("BUG", re.compile(r"\b(?:bug|glitch|crash(?:es|ed)?|error message|app freezes?)\b", re.I)),
    ("FEATURE_REQUEST", re.compile(r"\b(?:please add|wish(?: it)? had|would like (?:to )?see|request(?:ing)? (?:a )?feature)\b", re.I)),
    ("QUESTION", re.compile(r"\b(?:what|how|when|where|why|can|does|is)\b[^.!?\n]{0,180}\?", re.I)),
    ("USABILITY", re.compile(r"\b(?:hard to use|difficult to navigate|confusing|not intuitive|easy to use)\b", re.I)),
    ("PERFORMANCE", re.compile(r"\b(?:slow|laggy|lags|long loading|takes too long|unresponsive)\b", re.I)),
    ("SUPPORT", re.compile(r"\b(?:customer support|customer service|support team|support agent|support)\b", re.I)),
    ("PRICING", re.compile(r"\b(?:price|pricing|expensive|overpriced|too costly|subscription fee)\b", re.I)),
    ("CHURN", re.compile(r"\b(?:cancel(?:ling|ed)?|unsubscribe|switching away|leaving this product|stop using)\b", re.I)),
    ("PRIVACY", re.compile(r"\b(?:privacy|tracking me|excessive permissions|personal data exposure|data leak)\b", re.I)),
    ("FRAUD", re.compile(r"\b(?:fraud|scam|phishing|fraudulent charge|unauthori[sz]ed charge)\b", re.I)),
)


def _matches(pattern, text):
    return [
        {"text": match.group(0), "sourceSpan": [match.start(), match.end()]}
        for match in pattern.finditer(text)
    ]


def _configured_phrase_matches(text, phrases):
    found = []
    for phrase in phrases:
        pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.I)
        found.extend({"text": match.group(0), "sourceSpan": [match.start(), match.end()]}
                     for match in pattern.finditer(text))
    return found


def classify_feedback(text, competitor_terms=(), security_terms=()):
    """Return only explicit phrase-rule matches; no calibrated score is implied."""
    categories = []
    for category, pattern in _CATEGORY_RULES:
        evidence = _matches(pattern, text)
        if evidence:
            categories.append({
                "category": category,
                "classificationMethod": "deterministic_phrase_v1",
                "evidence": evidence,
            })

    competitive = _configured_phrase_matches(text, competitor_terms)
    if competitive:
        categories.append({
            "category": "COMPETITIVE",
            "classificationMethod": "configured_competitor_phrase_v1",
            "evidence": competitive,
        })

    security_keyword_matches = _configured_phrase_matches(text, security_terms)
    if security_keyword_matches:
        categories.append({
            "category": "SECURITY",
            "classificationMethod": "configured_security_phrase_v1",
            "evidence": security_keyword_matches,
        })

    for finding in extract_security_signals(text):
        category = (
            "FRAUD" if finding["findingType"] == "PAYMENT_FRAUD"
            else "PRIVACY" if finding["findingType"] == "PERSONAL_DATA_EXPOSURE"
            else "SECURITY"
        )
        if not any(item["category"] == category for item in categories):
            categories.append({
                "category": category,
                "classificationMethod": finding["classificationMethod"],
                "evidence": finding["evidence"],
            })

    if not categories:
        categories.append({
            "category": "OTHER",
            "classificationMethod": "no_configured_phrase_match_v1",
            "evidence": [],
        })
    return categories


def get_feedback_categories(project_id):
    entity = ProjectEntity.query.filter_by(project_id=project_id).first()
    competitor_terms = list(entity.competitor_keywords or []) if entity else []
    security_terms = list(entity.security_keywords or []) if entity else []
    reviews = Review.query.filter_by(project_id=project_id).filter(
        Review.deleted_at.is_(None), Review.is_spam.is_(False), Review.is_duplicate.is_(False)
    ).order_by(Review.created_at.desc()).limit(5000).all()

    items = []
    totals = {}
    for review in reviews:
        categories = classify_feedback(review.text or "", competitor_terms, security_terms)
        for category in categories:
            totals[category["category"]] = totals.get(category["category"], 0) + 1
        items.append({
            "reviewId": str(review.id),
            "source": review.source,
            "origin": {
                "type": "data_source" if review.data_source_id else "dataset",
                "id": str(review.data_source_id or review.dataset_id),
            },
            "categories": categories,
        })

    result_limit = 500
    return {
        "items": items[:result_limit],
        "summary": {
            "reviewsScanned": len(reviews),
            "classifiedReviews": sum(1 for item in items if any(
                category["category"] != "OTHER" for category in item["categories"]
            )),
            "categoryCounts": totals,
        },
        "truncated": len(items) > result_limit,
        "resultLimit": result_limit,
        "limitations": [
            "This deterministic phrase classifier is a partial vocabulary, not a semantic or exhaustive classifier.",
            "A review can match multiple categories; counts therefore do not sum to review volume.",
            "OTHER means no configured rule matched; it is not a semantic judgement.",
            "Security-related phrases identify reported signals and do not verify incidents.",
            "At most 5,000 eligible project reviews are scanned, and at most 500 evidence records are returned.",
        ],
    }
