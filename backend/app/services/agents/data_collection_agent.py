"""Calls the existing Phase 6 collection service — no independent scraping
logic here. See app/services/collection_service.py for the actual policy/
SSRF/rate-limit enforcement this agent relies on entirely.
"""
from app.services.agents.base import BaseAgent, AgentResult
from app.services import collection_service


class DataCollectionAgent(BaseAgent):
    name = "data_collection_agent"
    description = "Collects new reviews from this project's enabled, policy-permitted data sources."
    required_permission = "manage_data_sources"
    critical = False  # a collection failure degrades to "use existing data" per the fallback-first principle

    def run(self, context):
        results = collection_service.collect_enabled_sources_for_project(
            context["project_id"], context["user_id"],
        )
        if not results:
            return AgentResult(
                self.name, "skipped",
                message="No enabled data sources to collect from — proceeding with existing data.",
            )

        failed = [r for r in results if r.get("status") == "failed"]
        total_inserted = sum(r.get("recordsInserted", 0) for r in results)
        warnings = [
            f"{r.get('sourceId')}: {r.get('safeErrorMessage')}" for r in failed if r.get("safeErrorMessage")
        ]

        return AgentResult(
            self.name, "completed",
            message=f"Collected from {len(results)} source(s), {total_inserted} review(s) inserted.",
            data={"sources": results, "totalInserted": total_inserted},
            warnings=warnings,
        )
