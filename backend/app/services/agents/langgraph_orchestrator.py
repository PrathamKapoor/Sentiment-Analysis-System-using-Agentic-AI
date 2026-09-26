"""LangGraph-backed workflow orchestrator (opt-in).

This is the LangGraph implementation of the workflow runner described in
``docs/phase7_deferred_issues.md`` (``PHASE7_DEFERRED_LANGGRAPH``). It runs
**side by side** with the plain-Python orchestrator in
``orchestrator.py``; it does not replace it.

Selected with the ``AGENTIC_ENGINE`` environment variable:

    AGENTIC_ENGINE=deterministic   # default — the original for-loop runner
    AGENTIC_ENGINE=langgraph       # this module

Both engines must produce the same ``(step_results, overall_status)`` for the
same input; ``tests/test_langgraph_orchestrator.py`` pins that equivalence so
flipping the switch can never silently change behaviour.

What LangGraph actually buys here
---------------------------------
* A real state machine with **conditional edges** instead of a hardcoded
  ``for`` loop, so an agent's outcome genuinely steers the next hop.
* Per-node state that is inspectable and serialisable, which is the
  prerequisite for checkpointed resume.
* A single declarative graph definition, so the topology is data rather than
  control flow.

What it deliberately does NOT buy, and why
------------------------------------------
* **No LLM in the loop.** There is no model, no planner, no tool-calling and
  no ReAct loop. Every node is the *same* existing ``BaseAgent`` subclass
  calling the *same* existing service. Swapping the runner must not change a
  single analytical result.
* **No new trust boundary.** Agents still receive only the nine explicitly
  named internal services. Nothing here grants shell, SQL, filesystem or
  arbitrary-HTTP access.
* **No new persistence.** Durable workflow state stays in the
  ``agent_workflows`` table (AGENTS.md §13 forbids moving it to Python-only
  memory), and a LangGraph checkpointer is *not* attached by default: adding
  SqliteSaver/PostgresSaver would mean a 26th table and a second source of
  truth for workflow state. The human approval gate is therefore still the
  existing ``waiting_for_approval`` column plus the existing
  approve/resume/reject endpoints, not ``interrupt()``.
* **No background execution.** The graph is still invoked synchronously from
  ``workflow_service.start_workflow`` inside the HTTP request.

Adding an LLM decision to any node is a separate, explicitly-approved phase
(``AGENTS.md`` §15 and §16 still govern it), not a side effect of this file.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.agents.orchestrator import (
    AGENT_REGISTRY,
    BLOCKS_ON_FAILURE,
    STEP_ORDER,
    compute_overall_status,
    resolve_steps,
)

# The node name used for each agent step. Kept distinct from the step key so
# the graph's node names read as graph nodes rather than agent keys.
_NODE_PREFIX = "run_"
_TERMINAL_NODE = "finalize"


class WorkflowState(TypedDict, total=False):
    """Graph state.

    Mirrors exactly the locals of the deterministic runner's loop so the two
    engines cannot drift: same inputs, same outputs, same ordering.
    """

    # inputs
    workflow_type: str
    context: dict[str, Any]
    options: dict[str, Any]
    # planning output
    steps_to_run: dict[str, bool]
    step_options: dict[str, Any]
    remaining: list[str]
    # accumulators
    step_results: list[dict[str, Any]]
    blocked: list[str]
    # terminal
    overall_status: str


def _node_name(step_key: str) -> str:
    return f"{_NODE_PREFIX}{step_key}"


def _plan(state: WorkflowState) -> dict[str, Any]:
    """Resolve which steps run, and in what order.

    Delegates to the deterministic orchestrator's own ``resolve_steps`` so
    workflow-type defaults and the forced-``data_quality`` rule can never
    diverge between engines.
    """
    options = state.get("options") or {}
    steps_to_run = resolve_steps(state["workflow_type"], options)
    return {
        "steps_to_run": steps_to_run,
        "step_options": options.get("stepOptions") or {},
        "remaining": [k for k in STEP_ORDER if steps_to_run.get(k)],
        "step_results": [],
        "blocked": [],
    }


def _make_agent_node(step_key: str):
    """Build one graph node that runs one existing agent.

    The node body is intentionally identical to the deterministic loop body:
    build the agent, merge in the per-step parameters, call ``execute()``,
    append the serialised result, and record downstream blocking.
    """

    def node(state: WorkflowState) -> dict[str, Any]:
        # Retire this step first, unconditionally, so the graph can never
        # re-route back to a node that has already run.
        remaining = list(state.get("remaining") or [])
        if remaining:
            remaining.pop(0)
        update: dict[str, Any] = {"remaining": remaining}

        if step_key in (state.get("blocked") or []):
            # A required upstream step failed. Recorded as skipped, exactly
            # like the deterministic runner, and the node still "runs" so the
            # step appears in the persisted step list.
            update["step_results"] = (state.get("step_results") or []) + [
                {
                    "agent": f"{step_key}_agent",
                    "status": "skipped",
                    "message": "Skipped because a required upstream step failed.",
                    "data": {},
                    "warnings": [],
                }
            ]
            return update

        agent = AGENT_REGISTRY[step_key]()
        step_context = {
            **(state.get("context") or {}),
            "parameters": (state.get("step_options") or {}).get(step_key, {}),
        }
        result = agent.execute(step_context)

        blocked = list(state.get("blocked") or [])
        if result.status == "failed" and step_key in BLOCKS_ON_FAILURE:
            blocked.extend(BLOCKS_ON_FAILURE[step_key])

        update["step_results"] = (state.get("step_results") or []) + [
            result.to_dict()
        ]
        update["blocked"] = blocked
        return update

    node.__name__ = _node_name(step_key)
    return node


def _finalize(state: WorkflowState) -> dict[str, Any]:
    return {"overall_status": compute_overall_status(state.get("step_results") or [])}


def _route_next(state: WorkflowState) -> str:
    """Conditional edge: the next graph node, or the terminal node.

    This is the part that is genuinely a graph rather than a loop — the next
    hop is decided from state. Each agent node retires its own step from
    ``remaining`` (see ``_make_agent_node``), so this always advances.
    """
    remaining = state.get("remaining") or []
    if not remaining:
        return _TERMINAL_NODE
    return _node_name(remaining[0])


def build_graph():
    """Compile the workflow graph.

    Topology::

        START -> plan -> run_<step 1> -> ... -> run_<step n> -> finalize -> END

    with a conditional edge after ``plan`` and after every agent node, so the
    graph re-decides its next hop from state each time rather than relying on
    a hardcoded sequence. The *set* of steps still comes from
    ``resolve_steps``, which keeps step ordering a single source of truth.
    """
    graph = StateGraph(WorkflowState)

    graph.add_node("plan", _plan)
    graph.add_node(_TERMINAL_NODE, _finalize)
    for step_key in STEP_ORDER:
        graph.add_node(_node_name(step_key), _make_agent_node(step_key))

    graph.add_edge(START, "plan")

    # Every hop is conditional: `plan` and each agent node ask `_route_next`
    # where to go. `_consume_step` is folded into the routing nodes so the
    # step is only retired after it has actually been attempted.
    for source in ["plan"] + [_node_name(k) for k in STEP_ORDER]:
        graph.add_conditional_edges(
            source,
            _route_next,
            {
                **{_node_name(k): _node_name(k) for k in STEP_ORDER},
                _TERMINAL_NODE: _TERMINAL_NODE,
            },
        )

    graph.add_edge(_TERMINAL_NODE, END)

    return graph.compile()


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_workflow(workflow_type, context, options):
    """Drop-in replacement for ``orchestrator.run_workflow``.

    Returns the same ``(step_results, overall_status)`` tuple. Agent failures
    are still absorbed by ``BaseAgent.execute()``; only a genuine
    orchestration-level error propagates, so ``workflow_service``'s
    outer failure handling keeps working unchanged.
    """
    result = _get_graph().invoke(
        {
            "workflow_type": workflow_type,
            "context": context,
            "options": options or {},
        },
        config={"recursion_limit": len(STEP_ORDER) * 4 + 10},
    )

    return list(result.get("step_results") or []), result.get(
        "overall_status"
    ) or compute_overall_status(result.get("step_results") or [])
