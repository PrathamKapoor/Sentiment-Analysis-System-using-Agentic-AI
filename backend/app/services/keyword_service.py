"""Keyword extraction — frequency counts over unigrams/bigrams, computed
dynamically per request (never persisted — the approved schema has no
keyword-storage table, and these numbers are cheap to recompute at Phase 2/3
data volumes).
"""
import re

from flask import current_app
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from app.models import Review, SentimentResult

_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")
MIN_TOKEN_LENGTH = 3


def _tokenize(text):
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _ngrams(tokens, n):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def extract_keywords(project_id, filters=None, include_bigrams=True, top_n=50, search=None):
    filters = filters or {}
    blocked = current_app.config["KEYWORD_BLOCKED_WORDS"]

    query = Review.query.filter_by(project_id=project_id).filter(
        Review.deleted_at.is_(None), Review.is_spam.is_(False)
    )
    if filters.get("dateFrom"):
        query = query.filter(Review.review_date >= filters["dateFrom"])
    if filters.get("dateTo"):
        query = query.filter(Review.review_date <= filters["dateTo"])
    if filters.get("sourceId"):
        query = query.filter(Review.data_source_id == filters["sourceId"])
    if filters.get("datasetId"):
        query = query.filter(Review.dataset_id == filters["datasetId"])
    reviews = query.all()

    review_ids = [r.id for r in reviews]
    sentiment_by_review = {}
    if review_ids:
        for result in SentimentResult.query.filter(SentimentResult.review_id.in_(review_ids)).all():
            sentiment_by_review[result.review_id] = result

    keyword_reviews = {}  # keyword -> list of review_id
    for review in reviews:
        tokens = [
            t for t in _tokenize(review.text)
            if t not in ENGLISH_STOP_WORDS and t not in blocked and len(t) >= MIN_TOKEN_LENGTH
        ]
        found = set(tokens)
        if include_bigrams:
            found.update(_ngrams(tokens, 2))
        for kw in found:
            keyword_reviews.setdefault(kw, []).append(review.id)

    if search:
        search_lower = search.lower()
        keyword_reviews = {k: v for k, v in keyword_reviews.items() if search_lower in k}

    keywords = []
    for kw, ids in keyword_reviews.items():
        counts = {"positive": 0, "negative": 0, "neutral": 0}
        score_sum = 0.0
        scored = 0
        for rid in ids:
            result = sentiment_by_review.get(rid)
            if result:
                counts[result.sentiment_label] += 1
                score_sum += float(result.positive_score) - float(result.negative_score)
                scored += 1

        if counts["positive"] > counts["negative"] and counts["positive"] > counts["neutral"]:
            majority = "positive"
        elif counts["negative"] > counts["positive"] and counts["negative"] > counts["neutral"]:
            majority = "negative"
        elif scored == 0:
            majority = "unanalysed"
        else:
            majority = "neutral"

        keywords.append({
            "keyword": kw,
            "frequency": len(ids),
            "sentiment": majority,
            "averageSentimentScore": round(score_sum / scored, 4) if scored else None,
            "positiveCount": counts["positive"],
            "negativeCount": counts["negative"],
            "neutralCount": counts["neutral"],
        })

    keywords.sort(key=lambda k: k["frequency"], reverse=True)
    return keywords[:top_n]


def word_cloud_data(project_id, filters=None, top_n=100):
    keywords = extract_keywords(project_id, filters=filters, top_n=top_n)
    return [
        {"text": kw["keyword"], "value": kw["frequency"], "sentiment": kw["sentiment"]}
        for kw in keywords
    ]
