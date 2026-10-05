"""Fixed project-scoped tools exposed to the bounded investigation planner."""
from dataclasses import dataclass
from uuid import UUID

from app.errors.exceptions import NotFoundError, ValidationError
from app.models import Project, Review, SecurityFinding


MAX_TOOL_CALLS = 12
MAX_EVIDENCE = 80
MAX_SEARCH_LIMIT = 30
REQUIRED_ARGUMENTS = {"search_reviews": {"query"}, "get_review": {"evidenceId"},
                      "get_evidence": {"evidenceId"}}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    required_permission: str
    argument_keys: dict


TOOLS = {
    "get_project": Tool("get_project", "Read the selected project identity.", "view_reviews", {}),
    "search_reviews": Tool("search_reviews", "Find eligible reviews by literal text.", "view_reviews", {"query": str, "limit": int}),
    "get_review": Tool("get_review", "Read one eligible review by evidence ID.", "view_reviews", {"evidenceId": str}),
    "get_evidence": Tool("get_evidence", "Read one eligible evidence record by ID.", "view_reviews", {"evidenceId": str}),
    "get_sentiment": Tool("get_sentiment", "Read stored deterministic sentiment summary.", "view_reviews", {}),
    "get_topics": Tool("get_topics", "Read deterministic project topics.", "view_reviews", {}),
    "get_aspects": Tool("get_aspects", "Read stored aspect analysis.", "view_reviews", {}),
    "get_trends": Tool("get_trends", "Read stored sentiment trends.", "view_reviews", {"granularity": str}),
    "get_feedback_categories": Tool("get_feedback_categories", "Read phrase-based feedback category evidence.", "view_reviews", {}),
    "get_competitors": Tool("get_competitors", "Read configured competitor mention evidence.", "view_reviews", {}),
    "get_security_findings": Tool("get_security_findings", "Read project-scoped customer-reported security findings.", "view_reviews", {}),
    "get_security_indicators": Tool("get_security_indicators", "Read observed security indicators; no reputation judgement.", "view_reviews", {}),
    "get_incidents": Tool("get_incidents", "Read deterministic security correlation patterns.", "view_reviews", {}),
    "get_emerging_themes": Tool("get_emerging_themes", "Compare deterministic category/aspect counts across periods.", "view_reviews", {"days": int, "baselineDays": int}),
    "get_anomalies": Tool("get_anomalies", "Compare deterministic eligible review/category rates across periods.", "view_reviews", {"days": int, "baselineDays": int}),
    "get_root_cause_evidence": Tool("get_root_cause_evidence", "Read evidence-layered facts, changes, version overlaps, and explicitly non-causal hypotheses.", "view_reviews", {"days": int, "baselineDays": int}),
    "get_source_statistics": Tool("get_source_statistics", "Read per-source record composition and limitations.", "view_reviews", {}),
}


def _validate_args(name, args):
    tool = TOOLS.get(name)
    if tool is None or not isinstance(args, dict):
        raise ValidationError("Unknown investigation tool or invalid arguments")
    if set(args) - set(tool.argument_keys):
        raise ValidationError("Unexpected investigation tool argument")
    missing = REQUIRED_ARGUMENTS.get(name, set()) - set(args)
    if missing:
        raise ValidationError("Required investigation tool arguments are missing")
    for key, kind in tool.argument_keys.items():
        if key not in args:
            continue
        if kind is int and (isinstance(args[key], bool) or not isinstance(args[key], int)):
            raise ValidationError(f"{key} must be an integer")
        if kind is str and (not isinstance(args[key], str) or len(args[key]) > 500):
            raise ValidationError(f"{key} must be a string of at most 500 characters")
    if name == "search_reviews":
        query = args.get("query", "").strip()
        if not 2 <= len(query) <= 200:
            raise ValidationError("query must contain 2 to 200 characters")
        args["query"] = query
        args["limit"] = max(1, min(args.get("limit", 10), MAX_SEARCH_LIMIT))
    if name in {"get_trends"} and args.get("granularity", "weekly") not in {"daily", "weekly", "monthly"}:
        raise ValidationError("granularity is invalid")
    for key in ("days", "baselineDays"):
        if key in args:
            args[key] = max(1, min(args[key], 180))
    return args


def execute_tool(name, arguments, *, project_id, membership):
    """Validate the model request and derive all tenant scope server-side."""
    from app.services.permission_service import has_permission
    tool = TOOLS.get(name)
    if tool is None:
        raise ValidationError("Tool is not registered")
    if not has_permission(membership, tool.required_permission):
        raise ValidationError("Tool permission is unavailable")
    args = _validate_args(name, dict(arguments or {}))
    project = Project.query.filter_by(id=project_id, organisation_id=membership.organisation_id).filter(
        Project.deleted_at.is_(None)
    ).first()
    if project is None:
        raise NotFoundError("Project not found")
    if name == "get_project":
        return {"project": {"id": str(project.id), "name": project.name,
                             "productOrTopic": project.product_or_topic}}
    if name in {"get_review", "get_evidence"}:
        from app.services.evidence_service import get_evidence
        try:
            UUID(args.get("evidenceId", ""))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("evidenceId must be a UUID")
        return {"items": [get_evidence(project_id, args["evidenceId"])]}
    if name == "search_reviews":
        from app.services.evidence_service import serialize_evidence, eligible_evidence_query
        rows = eligible_evidence_query(project_id).filter(Review.text.contains(args["query"], autoescape=True)).order_by(
            Review.created_at.desc()
        ).limit(args["limit"]).all()
        return {"items": [serialize_evidence(row) for row in rows]}
    if name == "get_sentiment":
        from app.services.sentiment_service import get_summary
        return get_summary(project_id, {})
    if name == "get_topics":
        from app.services.topic_service import list_topics
        return {"items": list_topics(project_id)}
    if name == "get_aspects":
        from app.services.aspect_service import list_aspects
        return {"items": list_aspects(project_id, {})}
    if name == "get_trends":
        from app.services.trend_service import get_trends
        return get_trends(project_id, args.get("granularity", "weekly"), {})
    if name == "get_feedback_categories":
        from app.services.feedback_intelligence_service import get_feedback_categories
        return get_feedback_categories(project_id)
    if name == "get_competitors":
        from app.services.competitor_intelligence_service import get_competitor_intelligence
        return get_competitor_intelligence(project_id)
    if name == "get_security_findings":
        return {"items": [item.to_dict() for item in SecurityFinding.query.join(
            Review, SecurityFinding.review_id == Review.id
        ).filter(SecurityFinding.project_id == project_id,
            SecurityFinding.organisation_id == membership.organisation_id,
            SecurityFinding.status != "stale", Review.deleted_at.is_(None),
            Review.is_spam.is_(False), Review.is_duplicate.is_(False)
        ).order_by(SecurityFinding.created_at.desc()).limit(200).all()]}
    if name == "get_security_indicators":
        from app.services.security_intelligence_service import get_project_security_indicators
        return {"items": get_project_security_indicators(project_id)}
    if name == "get_incidents":
        from app.services.security_intelligence_service import correlate_security_signals
        return {"items": correlate_security_signals(project_id)}
    if name == "get_emerging_themes":
        from app.services.temporal_intelligence_service import get_emerging_themes
        return get_emerging_themes(project_id, days=args.get("days", 7), baseline_days=args.get("baselineDays", 7))
    if name == "get_anomalies":
        from app.services.temporal_intelligence_service import get_anomalies
        return get_anomalies(project_id, days=args.get("days", 7), baseline_days=args.get("baselineDays", 7))
    if name == "get_root_cause_evidence":
        from app.services.root_cause_service import get_root_cause_evidence
        return get_root_cause_evidence(project_id, days=args.get("days", 7), baseline_days=args.get("baselineDays", 7))
    if name == "get_source_statistics":
        from app.services.source_statistics_service import get_source_statistics
        return get_source_statistics(project_id)
    raise ValidationError("Tool is not registered")


def tool_catalog():
    return [{"name": tool.name, "description": tool.description,
             "arguments": {key: ("integer" if kind is int else "string") for key, kind in tool.argument_keys.items()},
             "required": sorted(REQUIRED_ARGUMENTS.get(tool.name, set()))}
            for tool in TOOLS.values()]


def evidence_ids_from(value):
    ids = set()
    if isinstance(value, dict):
        candidate = value.get("evidenceId") or value.get("reviewId")
        if isinstance(candidate, str):
            try:
                ids.add(str(UUID(candidate)))
            except ValueError:
                pass
        for key, child in value.items():
            if key in {"evidenceIds", "supportingEvidenceIds"} and isinstance(child, list):
                for item in child:
                    try:
                        ids.add(str(UUID(str(item))))
                    except ValueError:
                        continue
            else:
                ids.update(evidence_ids_from(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(evidence_ids_from(child))
    return ids
