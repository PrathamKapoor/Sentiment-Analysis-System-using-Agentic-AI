"""Persistence + entry point for agent workflows. Routes call only this
module — never the orchestrator or an agent directly — mirroring the
Phase 6 rule "always go through the service layer" (see
docs/phase6_agent_handoff.md §5, the same principle applies here: policy/
tenant/permission enforcement belongs in one place).
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.errors.exceptions import ValidationError, ConflictError, ForbiddenError, NotFoundError
from app.models import AgentWorkflow, AiSummary
from app.models.agent_workflow import WORKFLOW_TYPES as WORKFLOW_TYPE_NAMES
from app.services import ai_summary_service
from app.services.agents import orchestrator
from app.services.agents.report_agent import ReportAgent
from app.services.audit_service import log_action
from app.services.permission_service import has_permission

_TERMINAL_STATUS_ACTION = {
    "completed": "workflow.completed",
    "completed_with_warnings": "workflow.completed_with_warnings",
    "failed": "workflow.failed",
    "waiting_for_approval": "workflow.waiting_for_approval",
}


def _active_orchestrator():
    """Return the orchestrator module selected by AGENTIC_ENGINE.

    "deterministic" (default) is the original plain-Python for-loop runner.
    "langgraph" is the StateGraph implementation. Both are step-for-step
    equivalent and neither contains an LLM — this choice only affects how the
    workflow is walked, never what an agent computes.

    The LangGraph module is imported lazily so that the default
    (deterministic) path has no import-time dependency on it, and so a broken
    or missing LangGraph install can never take down the production runner.
    """
    engine = (current_app.config.get("AGENTIC_ENGINE") or "deterministic").lower()
    if engine == "langgraph":
        try:
            from app.services.agents import langgraph_orchestrator

            return langgraph_orchestrator
        except ImportError:
            # Fail safe and loudly: fall back to the deterministic runner
            # rather than erroring the request, but leave a trace so the
            # misconfiguration is discoverable.
            current_app.logger.exception(
                "AGENTIC_ENGINE=langgraph but the LangGraph orchestrator could "
                "not be imported; falling back to the deterministic runner."
            )
            return orchestrator
    return orchestrator


def _build_context(project, actor_user_id, membership, workflow_id):
    return {
        "organisation_id": project.organisation_id,
        "project_id": project.id,
        "user_id": actor_user_id,
        "membership": membership,
        "workflow_id": workflow_id,
    }


def _log_steps(project, actor_user_id, workflow_id, step_results):
    for step in step_results:
        action = {
            "completed": "agent.completed", "failed": "agent.failed",
            "skipped": "agent.skipped", "waiting_for_approval": "approval.requested",
        }.get(step["status"], "agent.completed")
        log_action(project.organisation_id, actor_user_id, action, "agent_workflow", workflow_id, {
            "agent": step["agent"], "status": step["status"],
        })


def start_workflow(project, actor_user_id, membership, workflow_type, options, idempotency_key=None):
    if workflow_type not in WORKFLOW_TYPE_NAMES:
        raise ValidationError(f"workflowType must be one of: {', '.join(WORKFLOW_TYPE_NAMES)}")
    options = options or {}

    if idempotency_key:
        existing = AgentWorkflow.query.filter_by(
            project_id=project.id, idempotency_key=idempotency_key,
        ).first()
        if existing is not None:
            return existing  # idempotent replay — never start a second run for the same key

    workflow = AgentWorkflow(
        project_id=project.id, workflow_type=workflow_type, status="running",
        options=options, idempotency_key=idempotency_key, started_by=actor_user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(workflow)
    db.session.flush()

    log_action(project.organisation_id, actor_user_id, "workflow.started", "agent_workflow", workflow.id, {
        "workflowType": workflow_type,
    })
    db.session.commit()

    context = _build_context(project, actor_user_id, membership, workflow.id)
    try:
        step_results, overall_status = _active_orchestrator().run_workflow(
            workflow_type, context, options
        )
    except Exception:
        # Every individual agent already catches its own exceptions
        # (BaseAgent.execute -> "failed" AgentResult) — this only catches a
        # genuine orchestration-level bug. Without this, the row above
        # would stay "running" forever: never leave a workflow in a
        # non-terminal status after a known failure.
        workflow.status = "failed"
        workflow.completed_at = datetime.now(timezone.utc)
        workflow.result_summary = {"steps": [], "warnings": ["The workflow failed due to an unexpected internal error."]}
        db.session.commit()
        log_action(project.organisation_id, actor_user_id, "workflow.failed", "agent_workflow", workflow.id, {})
        db.session.commit()
        return workflow

    warnings = [w for step in step_results for w in step.get("warnings", [])]
    workflow.status = overall_status
    workflow.completed_at = datetime.now(timezone.utc)
    workflow.result_summary = {"steps": step_results, "warnings": warnings}
    db.session.commit()

    _log_steps(project, actor_user_id, workflow.id, step_results)
    log_action(
        project.organisation_id, actor_user_id,
        _TERMINAL_STATUS_ACTION.get(overall_status, "workflow.completed"),
        "agent_workflow", workflow.id, {"status": overall_status},
    )
    db.session.commit()
    return workflow


def list_workflows(project_id):
    return AgentWorkflow.query.filter_by(project_id=project_id).order_by(
        AgentWorkflow.created_at.desc()
    ).all()


def _find_summary_id(workflow):
    step = next((s for s in workflow.result_summary.get("steps", []) if s["agent"] == "summary_agent"), None)
    return (step or {}).get("data", {}).get("summaryId")


def cancel_workflow(workflow, actor_user_id):
    if workflow.status != "waiting_for_approval":
        raise ConflictError("Only a workflow waiting for approval can be cancelled.")
    workflow.status = "cancelled"
    workflow.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action(workflow.project.organisation_id, actor_user_id, "workflow.cancelled", "agent_workflow", workflow.id)
    db.session.commit()
    return workflow


def approve_workflow(workflow, actor_user_id, membership):
    if workflow.status != "waiting_for_approval":
        raise ConflictError("This workflow is not waiting for approval.")
    if not has_permission(membership, "approve_ai_output"):
        raise ForbiddenError("Missing required permission: approve_ai_output")

    summary_id = _find_summary_id(workflow)
    if not summary_id:
        raise ConflictError("No pending summary found for this workflow.")
    summary = AiSummary.query.filter_by(id=summary_id, project_id=workflow.project_id).first()
    if summary is None:
        raise NotFoundError("Summary not found")

    ai_summary_service.approve_summary(summary, actor_user_id)
    log_action(workflow.project.organisation_id, actor_user_id, "approval.approved", "agent_workflow", workflow.id, {
        "summaryId": summary_id,
    })
    db.session.commit()
    return workflow


def reject_workflow(workflow, actor_user_id, membership, reason=None):
    if workflow.status != "waiting_for_approval":
        raise ConflictError("This workflow is not waiting for approval.")
    if not has_permission(membership, "approve_ai_output"):
        raise ForbiddenError("Missing required permission: approve_ai_output")

    summary_id = _find_summary_id(workflow)
    if summary_id:
        summary = AiSummary.query.filter_by(id=summary_id, project_id=workflow.project_id).first()
        if summary is not None:
            ai_summary_service.reject_summary(summary, actor_user_id, reason=reason)

    workflow.status = "cancelled"
    workflow.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action(workflow.project.organisation_id, actor_user_id, "approval.rejected", "agent_workflow", workflow.id)
    db.session.commit()
    return workflow


def resume_workflow(workflow, actor_user_id, membership):
    if workflow.status != "waiting_for_approval":
        raise ConflictError("Only a workflow waiting for approval can be resumed.")

    summary_id = _find_summary_id(workflow)
    summary = AiSummary.query.filter_by(id=summary_id, project_id=workflow.project_id).first() if summary_id else None
    if summary is None or summary.approval_status != "approved":
        raise ConflictError("Approve the pending summary before resuming this workflow.")

    context = _build_context(workflow.project, actor_user_id, membership, workflow.id)
    step_options = (workflow.options or {}).get("stepOptions") or {}
    result = ReportAgent().execute({**context, "parameters": step_options.get("report", {})})

    steps = [s for s in workflow.result_summary.get("steps", []) if s["agent"] != "report_agent"]
    steps.append(result.to_dict())
    warnings = [w for step in steps for w in step.get("warnings", [])]

    overall_status = "completed" if result.status == "completed" else "completed_with_warnings"
    workflow.status = overall_status
    workflow.completed_at = datetime.now(timezone.utc)
    workflow.result_summary = {"steps": steps, "warnings": warnings}
    db.session.commit()

    log_action(workflow.project.organisation_id, actor_user_id, "workflow.resumed", "agent_workflow", workflow.id, {
        "status": overall_status,
    })
    db.session.commit()
    return workflow
