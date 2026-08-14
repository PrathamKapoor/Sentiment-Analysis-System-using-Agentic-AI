"""Topic analysis: TF-IDF + MiniBatchKMeans, chosen over an LLM specifically
because it's small, deterministic, and easy to explain end-to-end (vectorize
-> cluster -> take each cluster's highest-weight terms as its name) — every
step is inspectable, which matters more here than marginal topic quality.

Re-running topic analysis for a project replaces its previous topics/
review_topics rather than versioning them, same "replace on re-run" design
already used for sentiment_results and consistent with "do not create
undocumented version-history tables."
"""
from flask import current_app
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans

from app.extensions import db
from app.errors.exceptions import ValidationError
from app.models import Topic, ReviewTopic, SentimentResult
from app.services.sentiment_service import eligible_reviews_query
from app.services.audit_service import log_action

MIN_REVIEWS_FOR_CLUSTERING = 2
TOP_TERMS_PER_TOPIC = 3


def run_topic_analysis(project_id, organisation_id, actor_user_id, topic_count=None):
    log_action(organisation_id, actor_user_id, "topic_analysis.started", "project", project_id, {})
    db.session.commit()

    try:
        reviews = eligible_reviews_query(project_id).all()
        texts = [r.text for r in reviews if r.text and r.text.strip()]
        reviews = [r for r in reviews if r.text and r.text.strip()]

        if len(texts) < MIN_REVIEWS_FOR_CLUSTERING:
            raise ValidationError(
                f"Not enough reviews for topic analysis — at least {MIN_REVIEWS_FOR_CLUSTERING} "
                "with usable text are required."
            )

        default_k = current_app.config["DEFAULT_TOPIC_COUNT"]
        max_k = current_app.config["MAX_TOPIC_COUNT"]
        k = min(topic_count or default_k, max_k, len(texts))
        k = max(k, 1)

        assignments, topic_terms, relevance = _cluster(texts, k)

        # Replace this project's previous topic set.
        Topic.query.filter_by(project_id=project_id).delete()
        db.session.flush()

        created_topics = {}
        seen_names = set()
        for cluster_id, terms in topic_terms.items():
            name = " / ".join(terms) if terms else f"Topic {cluster_id + 1}"
            # Two clusters can legitimately produce the same top-terms name
            # (tied/overlapping TF-IDF weights) — the schema's uq_topic_
            # project_name constraint requires uniqueness within one run,
            # so disambiguate rather than letting the insert fail.
            if name in seen_names:
                suffix = 2
                while f"{name} ({suffix})" in seen_names:
                    suffix += 1
                name = f"{name} ({suffix})"
            seen_names.add(name)
            topic = Topic(project_id=project_id, name=name)
            db.session.add(topic)
            db.session.flush()
            created_topics[cluster_id] = topic

        for review, cluster_id, score in zip(reviews, assignments, relevance):
            db.session.add(ReviewTopic(
                review_id=review.id,
                topic_id=created_topics[cluster_id].id,
                relevance_score=round(float(score), 4),
            ))

        log_action(organisation_id, actor_user_id, "topic_analysis.completed", "project", project_id, {
            "topicCount": len(created_topics), "reviewsClustered": len(reviews),
        })
        db.session.commit()
    except ValidationError:
        db.session.rollback()
        log_action(organisation_id, actor_user_id, "topic_analysis.failed", "project", project_id, {
            "error": "insufficient_data",
        })
        db.session.commit()
        raise
    except Exception as exc:
        db.session.rollback()
        log_action(organisation_id, actor_user_id, "topic_analysis.failed", "project", project_id, {
            "error": str(exc),
        })
        db.session.commit()
        raise

    return {"topicCount": len(created_topics), "reviewsClustered": len(reviews)}


def _cluster(texts, k):
    """Returns (cluster_assignment_per_text, {cluster_id: [top terms]}, relevance_per_text).

    Falls back to a single "General Feedback" cluster if TF-IDF produces a
    degenerate (all-zero / singular) matrix — e.g. every review is just
    stopwords — rather than letting sklearn raise past this function.
    """
    vectorizer = TfidfVectorizer(stop_words="english", max_features=500, min_df=1)
    try:
        matrix = vectorizer.fit_transform(texts)
        if matrix.shape[1] == 0:
            raise ValueError("empty vocabulary after stopword removal")
    except ValueError:
        return [0] * len(texts), {0: ["General Feedback"]}, [1.0] * len(texts)

    k = min(k, matrix.shape[0])
    model = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=3)
    labels = model.fit_predict(matrix)

    terms = vectorizer.get_feature_names_out()
    topic_terms = {}
    for cluster_id in range(k):
        centroid = model.cluster_centers_[cluster_id]
        top_indices = centroid.argsort()[::-1][:TOP_TERMS_PER_TOPIC]
        topic_terms[cluster_id] = [terms[i] for i in top_indices if centroid[i] > 0]

    # Relevance = cosine similarity of each doc to its assigned cluster centroid
    # (TF-IDF vectors are already L2-normalized, so a plain dot product works).
    relevance = []
    for i, cluster_id in enumerate(labels):
        doc_vector = matrix[i]
        centroid = model.cluster_centers_[cluster_id]
        score = float(doc_vector.multiply(centroid).sum())
        relevance.append(max(0.0, min(1.0, score)))

    return list(labels), topic_terms, relevance


def list_topics(project_id):
    topics = Topic.query.filter_by(project_id=project_id).all()
    result = []
    for topic in topics:
        review_count = len(topic.review_links)
        result.append(topic.to_dict(review_count=review_count))
    return result


def get_topic_with_sentiment(topic):
    review_ids = [link.review_id for link in topic.review_links]
    counts = {"positive": 0, "negative": 0, "neutral": 0, "unanalysed": 0}
    if review_ids:
        results = SentimentResult.query.filter(SentimentResult.review_id.in_(review_ids)).all()
        analysed_ids = {r.review_id for r in results}
        for r in results:
            counts[r.sentiment_label] += 1
        counts["unanalysed"] = len(review_ids) - len(analysed_ids)

    body = topic.to_dict(review_count=len(review_ids))
    body["sentimentDistribution"] = counts
    return body


def list_topic_reviews(topic):
    return [link.review for link in topic.review_links]
