"""Calls the existing Phase 5 report-generation service directly. Only
runs when a workflow explicitly requests it — never automatically, and
never distributes the resulting file externally (no such capability
exists to call).

If the report was asked to include the AI summary section but no summary
for this project has been approved yet, this agent does NOT silently
generate the report without it, and does NOT approve a draft on its own
(that would be the agent approving its own upstream output, which is
explicitly forbidden). It instead returns "waiting_for_approval" so the
orchestrator can surface that to a human — see workflow_service.py's
approve/resume flow.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import report_service
from app.services.report_data_service import ALL_SECTIONS
from app.services.agents._dates import resolve_date_range
from app.models import AiSummary

_DEFAULT_SECTIONS = [
    "projectOverview", "executiveSummary", "sentimentDistribution",
    "topicAnalysis", "aspectSentiment", "recommendations", "alerts", "conclusion",
]


class ReportAgent(BaseAgent):
    name = "report_agent"
    description = "Generates a PDF/Excel report from current, already-approved data. Only runs when requested."
    required_permission = "generate_report"
    critical = False

    def run(self, context):
        params = context.get("parameters") or {}
        project_id = context["project_id"]

        sections = [s for s in (params.get("sections") or _DEFAULT_SECTIONS) if s in ALL_SECTIONS]
        date_from, date_to = resolve_date_range(project_id, params)
        include_ai_summary = params.get("includeAiSummary", True)

        if include_ai_summary:
            has_approved_summary = AiSummary.query.filter_by(
                project_id=project_id, approval_status="approved",
            ).first() is not None
            if not has_approved_summary:
                return AgentResult(
                    self.name, "waiting_for_approval",
                    message="This report requested the AI summary section, but no approved summary "
                            "exists yet for this project. Approve the generated draft summary, then "
                            "resume this workflow to generate the report.",
                    data={"reason": "no_approved_summary"},
                )

        data = {
            "reportName": params.get("reportName") or "Agent-Generated Report",
            "dateFrom": date_from, "dateTo": date_to,
            "sections": sections, "fileFormat": params.get("fileFormat", "pdf"),
            "includeAiSummary": include_ai_summary,
            "includeRecommendations": params.get("includeRecommendations", True),
            "includeRepresentativeReviews": params.get("includeRepresentativeReviews", False),
        }
        report = report_service.create_report(project_id, context["user_id"], data)
        return AgentResult(
            self.name, "completed",
            message=f"Generated a {report.file_format.upper()} report.",
            data={"reportId": str(report.id), "status": report.generation_status},
        )
