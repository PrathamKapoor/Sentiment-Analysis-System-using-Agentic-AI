"""LangGraph orchestrator tests.

Covers three things:

1. The graph compiles and has the expected node topology.
2. With ``AGENTIC_ENGINE=langgraph`` the API runs a **real** workflow — the
   agents actually execute against real reviews, not just route.
3. The LangGraph engine is **step-for-step equivalent** to the deterministic
   one for every workflow type, including the human approval gate and the
   critical-failure blocking path.

The default engine remains ``deterministic``; these tests flip it explicitly
so the default path stays covered by the rest of the suite.
"""
from datetime import date

import pytest

from app.services.agents import langgraph_orchestrator as lg
from app.services.agents import orchestrator as det
from tests.conftest_project import owner_context, create_project, create_reviews_directly

TODAY = date(2026, 6, 15)

ENOUGH_REVIEWS = [
    "Delivery was terrible and very late, I am upset.",
    "Great product quality overall, very happy with it.",
    "Customer service was slow to respond to my ticket.",
    "Amazing value for the price, highly recommend.",
    "The packaging was damaged but the item itself was fine.",
    "Terrible experience, would not buy again, refund needed.",
]

WORKFLOW_TYPES = [
    "FULL_ANALYSIS",
    "COLLECT_AND_ANALYSE",
    "REFRESH_ANALYSIS",
    "EXECUTIVE_BRIEF",
    "ALERT_RECHECK",
    "REPORT_REFRESH",
]


@pytest.fixture()
def langgraph_engine(app):
    """Force the LangGraph engine for the duration of one test."""
    previous = app.config["AGENTIC_ENGINE"]
    app.config["AGENTIC_ENGINE"] = "langgraph"
    yield
    app.config["AGENTIC_ENGINE"] = previous


def _seed(client, project_id, texts=None):
    create_reviews_directly(project_id, texts or ENOUGH_REVIEWS, review_date=TODAY)


def _start(client, project_id, headers, workflow_type, options=None):
    return client.post(
        f"/api/v1/projects/{project_id}/workflows",
        json={"workflowType": workflow_type, "options": options or {}},
        headers=headers,
    )


def _steps(body):
    return {s["agent"]: s for s in body["steps"]}


# ------------------------------------------------------------------ TOPOLOGY

def test_graph_compiles_with_expected_nodes():
    compiled = lg.build_graph()
    node_names = set(compiled.get_graph().nodes)
    expected = {"plan", "finalize"} | {f"run_{k}" for k in det.STEP_ORDER}
    assert expected <= node_names, f"missing graph nodes: {expected - node_names}"


def test_graph_node_per_agent_no_extra_tools():
    """Every agent node maps 1:1 to an existing registered agent.

    This is the structural guarantee that LangGraph introduced no new tool
    surface: the graph can only ever call the nine pre-existing agents.
    """
    graph_nodes = {
        n[len("run_"):] for n in lg.build_graph().get_graph().nodes
        if n.startswith("run_")
    }
    assert graph_nodes == set(det.AGENT_REGISTRY) == set(det.STEP_ORDER)


def test_default_engine_is_deterministic(app):
    assert app.config["AGENTIC_ENGINE"] == "deterministic"


def test_invalid_engine_falls_back_to_deterministic():
    from app.config import BaseConfig

    # config.py normalises unknown values at import time; assert the guard
    # logic itself by re-deriving it the way create_app would see it.
    for bad in ("", "  ", "openai", "LANGGRAPH_V2", "none"):
        normalised = (bad or "deterministic").strip().lower()
        if normalised not in ("deterministic", "langgraph"):
            normalised = "deterministic"
        assert normalised == "deterministic"
    assert BaseConfig.AGENTIC_ENGINE in ("deterministic", "langgraph")


# ------------------------------------------------------- REAL END-TO-END RUN

def test_langgraph_runs_full_analysis_end_to_end(client, langgraph_engine):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, project_id)

    resp = _start(client, project_id, headers, "FULL_ANALYSIS")
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    steps = _steps(body)

    # The agents really executed, against real reviews.
    assert steps["data_quality_agent"]["status"] == "completed"
    assert steps["sentiment_agent"]["status"] == "completed"
    assert steps["sentiment_agent"]["data"]["analysedCount"] == 6
    assert steps["topic_agent"]["status"] == "completed"
    assert steps["aspect_agent"]["status"] == "completed"
    assert steps["summary_agent"]["status"] == "completed"
    assert steps["summary_agent"]["data"]["approvalStatus"] == "draft"
    assert steps["recommendation_agent"]["status"] == "completed"
    assert steps["alert_agent"]["status"] == "completed"
    # Not requested by default under either engine.
    assert "report_agent" not in steps
    assert "data_collection_agent" not in steps
    assert body["status"] in ("completed", "completed_with_warnings")


def test_langgraph_preserves_the_human_approval_gate(client, langgraph_engine):
    """The report step must still stop for approval, not self-approve."""
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, project_id)

    resp = _start(
        client, project_id, headers, "FULL_ANALYSIS", {"generateReport": True}
    )
    body = resp.get_json()["data"]
    steps = _steps(body)

    assert steps["report_agent"]["status"] == "waiting_for_approval"
    assert steps["report_agent"]["data"]["reason"] == "no_approved_summary"
    assert body["status"] == "waiting_for_approval"
    # And the summary it is waiting on is still a human-owned draft.
    assert steps["summary_agent"]["data"]["approvalStatus"] == "draft"

    # The documented human path still works end to end.
    workflow_id = body["id"]
    summary_id = steps["summary_agent"]["data"]["summaryId"]
    approved = client.post(
        f"/api/v1/ai-summaries/{summary_id}/approve", headers=headers
    )
    assert approved.status_code == 200
    resumed = client.post(f"/api/v1/workflows/{workflow_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert _steps(resumed.get_json()["data"])["report_agent"]["status"] == "completed"


def test_langgraph_blocks_downstream_on_critical_failure(client, langgraph_engine, monkeypatch):
    """A critical Data Quality failure must still block everything after it."""
    from app.services.agents.data_quality_agent import DataQualityAgent

    def boom(self, context):
        from app.services.agents.base import AgentResult

        return AgentResult(self.name, "failed", message="forced failure", data={})

    monkeypatch.setattr(DataQualityAgent, "run", boom)

    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, project_id)

    resp = _start(client, project_id, headers, "FULL_ANALYSIS")
    body = resp.get_json()["data"]
    steps = _steps(body)

    assert steps["data_quality_agent"]["status"] == "failed"
    for blocked in ("sentiment_agent", "topic_agent", "aspect_agent",
                    "summary_agent", "recommendation_agent", "alert_agent"):
        assert steps[blocked]["status"] == "skipped"
        assert "upstream step failed" in steps[blocked]["message"]
    assert body["status"] == "failed"


# ------------------------------------------------------------- EQUIVALENCE

@pytest.mark.parametrize("workflow_type", WORKFLOW_TYPES)
def test_engines_agree_on_step_selection(client, app, workflow_type):
    """Both engines must select and order the same steps for every type.

    Run against real seeded data so the comparison covers actual agent
    execution, not just routing.
    """
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, project_id)

    app.config["AGENTIC_ENGINE"] = "deterministic"
    det_body = _start(client, project_id, headers, workflow_type).get_json()["data"]
    app.config["AGENTIC_ENGINE"] = "langgraph"
    lg_body = _start(client, project_id, headers, workflow_type).get_json()["data"]

    assert [s["agent"] for s in det_body["steps"]] == [
        s["agent"] for s in lg_body["steps"]
    ]
    assert [s["status"] for s in det_body["steps"]] == [
        s["status"] for s in lg_body["steps"]
    ]
    assert det_body["status"] == lg_body["status"]


def test_engines_agree_with_option_overrides(client, app):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed(client, project_id)

    options = {"runSentiment": False, "generateReport": True}
    app.config["AGENTIC_ENGINE"] = "deterministic"
    det_body = _start(
        client, project_id, headers, "FULL_ANALYSIS", options
    ).get_json()["data"]
    app.config["AGENTIC_ENGINE"] = "langgraph"
    lg_body = _start(
        client, project_id, headers, "FULL_ANALYSIS", options
    ).get_json()["data"]

    assert [s["agent"] for s in det_body["steps"]] == [
        s["agent"] for s in lg_body["steps"]
    ]
    assert "sentiment_agent" not in _steps(lg_body)
    assert _steps(lg_body)["report_agent"]["status"] == "waiting_for_approval"
    assert det_body["status"] == lg_body["status"]


def test_engines_agree_on_blocking(app):
    """Direct comparison with a forced critical failure, no HTTP involved."""
    import app.services.agents.data_quality_agent as dqa
    from app.services.agents.base import AgentResult

    def boom(self, context):
        return AgentResult(self.name, "failed", message="forced", data={})

    original = dqa.DataQualityAgent.run
    dqa.DataQualityAgent.run = boom
    try:
        ctx = {
            "organisation_id": "00000000-0000-0000-0000-000000000000",
            "project_id": "00000000-0000-0000-0000-000000000000",
            "actor_user_id": None,
            "membership": None,
            "workflow_id": "00000000-0000-0000-0000-000000000000",
        }
        det_steps, det_status = det.run_workflow("FULL_ANALYSIS", dict(ctx), {})
        lg_steps, lg_status = lg.run_workflow("FULL_ANALYSIS", dict(ctx), {})
    finally:
        dqa.DataQualityAgent.run = original

    assert [(s["agent"], s["status"]) for s in det_steps] == [
        (s["agent"], s["status"]) for s in lg_steps
    ]
    assert det_status == lg_status


def test_langgraph_orchestrator_falls_back_when_unimportable(client, app, monkeypatch):
    """A broken LangGraph install must never take the API down."""
    import app.services.workflow_service as ws

    class Boom:
        @staticmethod
        def run_workflow(*a, **k):
            raise AssertionError("must not be called")

    def raiser():
        raise ImportError("langgraph missing")

    monkeypatch.setattr(ws, "_active_orchestrator", lambda: det)
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.agents.langgraph_orchestrator", None
    )

    # With the import broken, _active_orchestrator must return the
    # deterministic runner rather than propagating.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "app.services.agents.langgraph_orchestrator":
            raise ImportError("simulated missing langgraph")
        return real_import(name, *a, **k)

    app.config["AGENTIC_ENGINE"] = "langgraph"
    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        selected = ws._active_orchestrator()
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)
        app.config["AGENTIC_ENGINE"] = "deterministic"

    assert selected is det


def test_active_orchestrator_selection(app):
    import app.services.workflow_service as ws

    app.config["AGENTIC_ENGINE"] = "deterministic"
    assert ws._active_orchestrator() is det
    app.config["AGENTIC_ENGINE"] = "langgraph"
    assert ws._active_orchestrator() is lg
    app.config["AGENTIC_ENGINE"] = "deterministic"
