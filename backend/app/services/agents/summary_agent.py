"""Calls the completed Phase 5 AI-summary system directly (which itself
calls the deterministic template engine — see app/services/agents/
provider.py for the provider-abstraction note on why this agent doesn't
call the provider directly: ai_summary_service.create_summary already
wraps generate_project_summary AND persists/audits the draft row, which
this agent needs so the resulting summary can later be approved through
the existing, unchanged approval workflow).

The generated summary is always created with approval_status="draft" —
this agent never approves its own output; only a human via the existing
POST /ai-summaries/{id}/approve endpoint (approve_ai_output permission)
can do that.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import ai_summary_service
from app.services.summary_service import SUMMARY_TYPES
from app.services.agents._dates import resolve_date_range


class SummaryAgent(BaseAgent):
    name = "summary_agent"
    description = "Generates a deterministic-template AI summary as a draft — never auto-approved."
    required_permission = "generate_report"
    critical = False

    def run(self, context):
        params = context.get("parameters") or {}
        project_id = context["project_id"]
        summary_type = params.get("summaryType", "executive")
        if summary_type not in SUMMARY_TYPES:
            summary_type = "executive"

        date_from, date_to = resolve_date_range(project_id, params)

        summary = ai_summary_service.create_summary(
            project_id, context["user_id"], summary_type, date_from, date_to,
        )
        return AgentResult(
            self.name, "completed",
            message=f"Generated a draft '{summary_type}' summary (awaiting human review/approval).",
            data={"summaryId": str(summary.id), "approvalStatus": summary.approval_status},
        )
