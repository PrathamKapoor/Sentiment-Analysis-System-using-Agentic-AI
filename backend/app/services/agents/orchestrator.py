"""Deterministic workflow orchestrator. No LangGraph — see
docs/phase7_deferred_issues.md PHASE7_DEFERRED_LANGGRAPH for why. This
module is intentionally plain Python control flow: a fixed step order, a
per-workflow-type default step selection, and a small blocked-steps map
for critical-agent failure — easy to read, easy to test, no new runtime
dependency, no risk of destabilising the rest of the app.
"""
from app.services.agents.data_collection_agent import DataCollectionAgent
from app.services.agents.data_quality_agent import DataQualityAgent
from app.services.agents.sentiment_agent import SentimentAgent
from app.services.agents.topic_agent import TopicAgent
from app.services.agents.aspect_agent import AspectAgent
from app.services.agents.summary_agent import SummaryAgent
from app.services.agents.recommendation_agent import RecommendationAgent
from app.services.agents.alert_agent import AlertAgent
from app.services.agents.report_agent import ReportAgent

STEP_ORDER = (
    "data_collection", "data_quality", "sentiment", "topic", "aspect",
    "summary", "recommendation", "alert", "report",
)

AGENT_REGISTRY = {
    "data_collection": DataCollectionAgent,
    "data_quality": DataQualityAgent,
    "sentiment": SentimentAgent,
    "topic": TopicAgent,
    "aspect": AspectAgent,
    "summary": SummaryAgent,
    "recommendation": RecommendationAgent,
    "alert": AlertAgent,
    "report": ReportAgent,
}

# A failure in one of these keys skips (does not attempt) the listed
# downstream steps, rather than letting them run against unreliable state.
BLOCKS_ON_FAILURE = {
    "data_quality": ["sentiment", "topic", "aspect", "summary", "recommendation", "alert", "report"],
    "sentiment": ["topic", "aspect"],
}

_NO_STEPS = {k: False for k in STEP_ORDER}

WORKFLOW_TYPES = {
    "FULL_ANALYSIS": {
        **_NO_STEPS, "data_quality": True, "sentiment": True, "topic": True,
        "aspect": True, "summary": True, "recommendation": True, "alert": True,
    },
    "COLLECT_AND_ANALYSE": {
        **_NO_STEPS, "data_collection": True, "data_quality": True, "sentiment": True,
        "topic": True, "aspect": True, "summary": True, "recommendation": True, "alert": True,
    },
    "REFRESH_ANALYSIS": {
        **_NO_STEPS, "data_quality": True, "sentiment": True, "topic": True, "aspect": True,
    },
    "EXECUTIVE_BRIEF": {
        **_NO_STEPS, "summary": True, "recommendation": True,
    },
    "ALERT_RECHECK": {
        **_NO_STEPS, "alert": True,
    },
    "REPORT_REFRESH": {
        **_NO_STEPS, "report": True,
    },
}

_OPTION_TO_STEP = {
    "collectNewData": "data_collection",
    "runSentiment": "sentiment",
    "runTopics": "topic",
    "runAspects": "aspect",
    "generateSummary": "summary",
    "generateRecommendations": "recommendation",
    "evaluateAlerts": "alert",
    "generateReport": "report",
}


def resolve_steps(workflow_type, options):
    """Workflow-type defaults, overridable per-step by explicit user
    options — "do not force every workflow to execute every agent."
    """
    steps = dict(WORKFLOW_TYPES[workflow_type])
    for option_key, step_key in _OPTION_TO_STEP.items():
        value = (options or {}).get(option_key)
        if value is not None:
            steps[step_key] = bool(value)
    # data_quality is free/cheap context for any analytical step — always
    # included alongside them rather than requiring a separate toggle.
    steps["data_quality"] = steps["data_quality"] or any(steps[k] for k in ("sentiment", "topic", "aspect"))
    return steps


def compute_overall_status(step_results):
    if not step_results:
        return "completed"
    if any(s["status"] == "waiting_for_approval" for s in step_results):
        return "waiting_for_approval"
    if any(s["status"] == "failed" and AGENT_REGISTRY[_agent_key(s["agent"])].critical for s in step_results):
        return "failed"
    if any(s["status"] in ("failed", "skipped") for s in step_results):
        return "completed_with_warnings"
    return "completed"


def _agent_key(agent_name):
    return agent_name.replace("_agent", "")


def run_workflow(workflow_type, context, options):
    """Runs every selected step in a fixed, dependency-respecting order.
    Returns (step_results: list[dict], overall_status: str). Never raises
    for an individual agent's failure — BaseAgent.execute() already
    converts exceptions into a "failed" AgentResult; this function only
    lets a genuinely unexpected orchestration-level error propagate.
    """
    steps_to_run = resolve_steps(workflow_type, options)
    step_options = (options or {}).get("stepOptions") or {}

    step_results = []
    blocked = set()

    for step_key in STEP_ORDER:
        if not steps_to_run.get(step_key):
            continue

        if step_key in blocked:
            step_results.append({
                "agent": f"{step_key}_agent", "status": "skipped",
                "message": "Skipped because a required upstream step failed.",
                "data": {}, "warnings": [],
            })
            continue

        agent = AGENT_REGISTRY[step_key]()
        step_context = {**context, "parameters": step_options.get(step_key, {})}
        result = agent.execute(step_context)
        step_results.append(result.to_dict())

        if result.status == "failed" and step_key in BLOCKS_ON_FAILURE:
            blocked.update(BLOCKS_ON_FAILURE[step_key])

    return step_results, compute_overall_status(step_results)
