from flask import Blueprint, request, g

from app.schemas.workflow_schemas import StartWorkflowSchema, RejectWorkflowSchema
from app.decorators.auth import project_access_required, permission_required, workflow_access_required
from app.services import workflow_service
from app.utils.responses import success_response

# Nested under /projects/{project_id}/workflows
project_workflows_bp = Blueprint("project_workflows", __name__)

# Top-level /workflows/{workflow_id}, matching the existing pattern for
# every other project-scoped resource (sources, datasets, reviews, ...).
workflows_bp = Blueprint("workflows", __name__)


@project_workflows_bp.route("", methods=["POST"])
@project_access_required
def start_workflow(project_id):
    """No single blanket permission gate here — each agent step checks its
    own existing permission and is skipped (not a hard 403) if the caller
    lacks it, so e.g. a Viewer can still run the read-only analysis steps
    of FULL_ANALYSIS. See app/services/agents/base.py::BaseAgent.can_run.
    """
    data = StartWorkflowSchema().load(request.get_json(force=True) or {})
    workflow = workflow_service.start_workflow(
        g.current_project, g.current_user.id, g.current_membership,
        data["workflowType"], data.get("options") or {}, idempotency_key=data.get("idempotencyKey"),
    )
    return success_response(workflow.to_dict(), message="Workflow started", status_code=201)


@project_workflows_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_workflows(project_id):
    workflows = workflow_service.list_workflows(project_id)
    return success_response({"items": [w.to_dict() for w in workflows]})


@workflows_bp.route("/<workflow_id>", methods=["GET"])
@workflow_access_required
@permission_required("view_reviews")
def get_workflow(workflow_id):
    return success_response(g.current_workflow.to_dict())


@workflows_bp.route("/<workflow_id>/steps", methods=["GET"])
@workflow_access_required
@permission_required("view_reviews")
def get_workflow_steps(workflow_id):
    return success_response({"items": g.current_workflow.to_dict()["steps"]})


@workflows_bp.route("/<workflow_id>/cancel", methods=["POST"])
@workflow_access_required
@permission_required("view_reviews")
def cancel_workflow(workflow_id):
    workflow = workflow_service.cancel_workflow(g.current_workflow, g.current_user.id)
    return success_response(workflow.to_dict(), message="Workflow cancelled")


@workflows_bp.route("/<workflow_id>/resume", methods=["POST"])
@workflow_access_required
@permission_required("view_reviews")
def resume_workflow(workflow_id):
    workflow = workflow_service.resume_workflow(g.current_workflow, g.current_user.id, g.current_membership)
    return success_response(workflow.to_dict(), message="Workflow resumed")


@workflows_bp.route("/<workflow_id>/approve", methods=["POST"])
@workflow_access_required
@permission_required("approve_ai_output")
def approve_workflow(workflow_id):
    workflow = workflow_service.approve_workflow(g.current_workflow, g.current_user.id, g.current_membership)
    return success_response(workflow.to_dict(), message="Approved")


@workflows_bp.route("/<workflow_id>/reject", methods=["POST"])
@workflow_access_required
@permission_required("approve_ai_output")
def reject_workflow(workflow_id):
    data = RejectWorkflowSchema().load(request.get_json(silent=True) or {})
    workflow = workflow_service.reject_workflow(
        g.current_workflow, g.current_user.id, g.current_membership, reason=data.get("reason"),
    )
    return success_response(workflow.to_dict(), message="Rejected")
