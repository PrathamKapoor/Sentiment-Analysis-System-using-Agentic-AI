from flask import Blueprint, request, g

from app.extensions import db
from app.errors.exceptions import NotFoundError
from app.schemas.analysis_schemas import (
    RunSentimentAnalysisSchema, RunTopicAnalysisSchema, RunAspectAnalysisSchema, ComparisonSchema,
)
from app.decorators.auth import project_access_required, permission_required
from app.services import (
    sentiment_service, topic_service, keyword_service, trend_service, aspect_service, comparison_service,
)
from app.models import Topic, Aspect
from app.utils.query_helpers import parse_analysis_filters, is_valid_uuid
from app.utils.responses import success_response

analysis_bp = Blueprint("analysis", __name__)


# ---- Sentiment ----

@analysis_bp.route("/sentiment", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def run_sentiment_analysis(project_id):
    data = RunSentimentAnalysisSchema().load(request.get_json(silent=True) or {})
    summary = sentiment_service.run_analysis(
        project_id, g.current_user.id,
        include_spam=data["includeSpam"], include_duplicates=data["includeDuplicates"],
    )
    return success_response(
        {"jobId": project_id, "status": "complete", **summary},
        message="Sentiment analysis job queued",
        status_code=202,
    )


@analysis_bp.route("/sentiment/reanalyse", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def reanalyse_sentiment(project_id):
    data = RunSentimentAnalysisSchema().load(request.get_json(silent=True) or {})
    summary = sentiment_service.run_analysis(
        project_id, g.current_user.id,
        include_spam=data["includeSpam"], include_duplicates=data["includeDuplicates"],
        force=True,
    )
    return success_response(
        {"jobId": project_id, "status": "complete", **summary},
        message="Sentiment re-analysis job queued",
        status_code=202,
    )


@analysis_bp.route("/sentiment", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_sentiment_results(project_id):
    filters = parse_analysis_filters(request.args)
    results = sentiment_service.list_results(project_id, filters, limit=500)
    return success_response({"items": [r.to_dict() for r in results]})


@analysis_bp.route("/sentiment/summary", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_sentiment_summary(project_id):
    filters = parse_analysis_filters(request.args)
    return success_response(sentiment_service.get_summary(project_id, filters))


# ---- Topics ----

@analysis_bp.route("/topics", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def run_topic_analysis(project_id):
    data = RunTopicAnalysisSchema().load(request.get_json(silent=True) or {})
    summary = topic_service.run_topic_analysis(
        project_id, g.current_organisation_id, g.current_user.id,
        topic_count=data.get("topicCount"),
    )
    return success_response(
        {"jobId": project_id, "status": "complete", **summary},
        message="Topic analysis complete",
        status_code=202,
    )


@analysis_bp.route("/topics", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_topics(project_id):
    return success_response({"items": topic_service.list_topics(project_id)})


def _get_project_topic_or_404(project_id, topic_id):
    if not is_valid_uuid(topic_id):
        raise NotFoundError("Topic not found")
    topic = Topic.query.filter_by(id=topic_id, project_id=project_id).first()
    if topic is None:
        raise NotFoundError("Topic not found")
    return topic


@analysis_bp.route("/topics/<topic_id>", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_topic(project_id, topic_id):
    topic = _get_project_topic_or_404(project_id, topic_id)
    return success_response(topic_service.get_topic_with_sentiment(topic))


@analysis_bp.route("/topics/<topic_id>/reviews", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_topic_reviews(project_id, topic_id):
    topic = _get_project_topic_or_404(project_id, topic_id)
    reviews = topic_service.list_topic_reviews(topic)
    return success_response({"items": [r.to_dict() for r in reviews]})


# ---- Keywords / word cloud ----

@analysis_bp.route("/keywords", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_keywords(project_id):
    filters = parse_analysis_filters(request.args)
    top_n = request.args.get("topN", default=50, type=int)
    search = request.args.get("search")
    keywords = keyword_service.extract_keywords(project_id, filters=filters, top_n=top_n, search=search)
    return success_response({"items": keywords})


@analysis_bp.route("/word-cloud", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_word_cloud(project_id):
    filters = parse_analysis_filters(request.args)
    top_n = request.args.get("topN", default=100, type=int)
    return success_response({"items": keyword_service.word_cloud_data(project_id, filters=filters, top_n=top_n)})


# ---- Trends ----

@analysis_bp.route("/trends", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_trends(project_id):
    filters = parse_analysis_filters(request.args)
    granularity = request.args.get("granularity", default="daily")
    return success_response(trend_service.get_trends(project_id, granularity, filters))


# ---- Aspects ----
# Generation permission: the approved REST API Spec documents no "generate"
# endpoint for aspects/recommendations at all (pre-dates this phase). No
# better-fitting catalogue permission exists for "AI generation" specifically
# (create_project/edit_project are project-management, not analysis;
# approve_ai_output is for reviewing output, not producing it). Reusing
# view_reviews, matching the already-approved pattern for triggering
# sentiment/topic analysis ("Role: view_reviews (trigger) — result
# generation is agent-driven"). Documented in the Phase 4 completion report.

@analysis_bp.route("/aspects", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def run_aspect_analysis(project_id):
    data = RunAspectAnalysisSchema().load(request.get_json(silent=True) or {})
    summary = aspect_service.run_aspect_analysis(
        project_id, g.current_user.id,
        include_spam=data["includeSpam"], include_duplicates=data["includeDuplicates"],
    )
    return success_response(
        {"jobId": project_id, "status": "complete", **summary},
        message="Aspect analysis complete", status_code=202,
    )


@analysis_bp.route("/aspects/reanalyse", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def reanalyse_aspects(project_id):
    data = RunAspectAnalysisSchema().load(request.get_json(silent=True) or {})
    summary = aspect_service.run_aspect_analysis(
        project_id, g.current_user.id,
        include_spam=data["includeSpam"], include_duplicates=data["includeDuplicates"],
        force=True,
    )
    return success_response(
        {"jobId": project_id, "status": "complete", **summary},
        message="Aspect re-analysis complete", status_code=202,
    )


@analysis_bp.route("/aspects", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_aspects(project_id):
    filters = parse_analysis_filters(request.args)
    min_freq = filters.get("minimumFrequency")
    return success_response({"items": aspect_service.list_aspects(project_id, filters, minimum_frequency=min_freq)})


def _get_project_aspect_or_404(project_id, aspect_id):
    if not is_valid_uuid(aspect_id):
        raise NotFoundError("Aspect not found")
    aspect = Aspect.query.filter_by(id=aspect_id, project_id=project_id).first()
    if aspect is None:
        raise NotFoundError("Aspect not found")
    return aspect


@analysis_bp.route("/aspects/<aspect_id>", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_aspect(project_id, aspect_id):
    aspect = _get_project_aspect_or_404(project_id, aspect_id)
    filters = parse_analysis_filters(request.args)
    return success_response(aspect_service.get_aspect_detail(aspect, filters))


@analysis_bp.route("/aspects/<aspect_id>/reviews", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_aspect_reviews(project_id, aspect_id):
    aspect = _get_project_aspect_or_404(project_id, aspect_id)
    filters = parse_analysis_filters(request.args)
    return success_response({"items": aspect_service.list_aspect_reviews(aspect, filters)})


# ---- Comparison ----

@analysis_bp.route("/comparison", methods=["POST"])
@project_access_required
@permission_required("view_reviews")
def run_comparison(project_id):
    data = ComparisonSchema().load(request.get_json(force=True) or {})
    result = comparison_service.compare_projects(
        g.current_organisation_id, data["targetProjectIds"],
        date_from=data.get("dateFrom"), date_to=data.get("dateTo"),
    )
    return success_response(result)
