from flask import Blueprint, request, g

from app.extensions import db
from app.schemas.review_schemas import UpdateReviewSchema, MarkSpamSchema
from app.decorators.auth import (
    project_access_required, permission_required, review_access_required,
)
from app.services import review_service, sentiment_service, aspect_service
from app.services.audit_service import log_action
from app.schemas.analysis_schemas import CorrectSentimentSchema
from app.utils.responses import success_response

project_reviews_bp = Blueprint("project_reviews", __name__)
reviews_bp = Blueprint("reviews", __name__)


def _review_dict_with_sentiment(review):
    body = review.to_dict()
    result = review.sentiment_result
    body["sentiment"] = result.to_dict() if result else None
    body["analysisStatus"] = "analysed" if result else "not_analysed"
    return body


@project_reviews_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_reviews(project_id):
    filters = {
        "source": request.args.get("source"),
        "rating": request.args.get("rating", type=float),
        "dateFrom": request.args.get("dateFrom"),
        "dateTo": request.args.get("dateTo"),
        "search": request.args.get("search"),
        "sentiment": request.args.get("sentiment"),
    }
    reviews = review_service.list_reviews(project_id, filters)
    return success_response({"items": [_review_dict_with_sentiment(r) for r in reviews]})


@reviews_bp.route("/<review_id>", methods=["GET"])
@review_access_required
@permission_required("view_reviews")
def get_review(review_id):
    return success_response(_review_dict_with_sentiment(g.current_review))


@reviews_bp.route("/<review_id>/sentiment", methods=["GET"])
@review_access_required
@permission_required("view_reviews")
def get_review_sentiment(review_id):
    result = sentiment_service.get_review_sentiment(g.current_review)
    return success_response(result.to_dict())


@reviews_bp.route("/<review_id>/aspects", methods=["GET"])
@review_access_required
@permission_required("view_reviews")
def get_review_aspects(review_id):
    return success_response({"items": aspect_service.list_review_aspects(g.current_review)})


@reviews_bp.route("/<review_id>/correct-sentiment", methods=["POST"])
@review_access_required
@permission_required("correct_sentiment")
def correct_review_sentiment(review_id):
    data = CorrectSentimentSchema().load(request.get_json(force=True) or {})
    result = sentiment_service.correct_sentiment(
        g.current_review, data["label"], g.current_user.id, data.get("reason")
    )
    db.session.commit()
    return success_response(result.to_dict(), message="Sentiment corrected")


@reviews_bp.route("/<review_id>", methods=["PATCH"])
@review_access_required
@permission_required("correct_sentiment")
def update_review(review_id):
    data = UpdateReviewSchema().load(request.get_json(force=True) or {})
    review = review_service.update_review(g.current_review, data)
    log_action(g.current_organisation_id, g.current_user.id, "review.update", "review", review.id, data)
    db.session.commit()
    return success_response(review.to_dict(), message="Review updated")


@reviews_bp.route("/<review_id>/mark-spam", methods=["POST"])
@review_access_required
@permission_required("correct_sentiment")
def mark_spam(review_id):
    data = MarkSpamSchema().load(request.get_json(force=True) or {})
    review = review_service.mark_spam(g.current_review, data["isSpam"])
    log_action(g.current_organisation_id, g.current_user.id, "review.mark_spam", "review", review.id, data)
    db.session.commit()
    return success_response(review.to_dict(), message="Review flagged as spam" if data["isSpam"] else "Spam flag cleared")
