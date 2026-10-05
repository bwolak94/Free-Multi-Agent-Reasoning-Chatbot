from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage  # noqa: TC002
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agents.planner import PlannerError, run_planner

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


class GraphState(TypedDict, total=False):
    """Full state passed through the LangGraph graph.

    Fields
    ------
    messages:       Conversation history (uses add_messages reducer).
    plan:           Ordered list of steps produced by the Planner node.
    current_step:   Index of the step currently being executed.
    artifacts:      Artifact metadata produced during execution.
    observations:   Collected tool/agent observations per step.
    iterations:     How many reflect->re-plan loops have occurred.
    hitl_config:    Human-in-the-loop approval gates (mirrors Thread.hitl_config).
    error:          Error message if the graph entered an error state.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[dict[str, Any]]
    current_step: int
    artifacts: list[dict[str, Any]]
    observations: list[str]
    iterations: int
    hitl_config: dict[str, Any] | None
    error: str | None
    pending_tool: dict[str, Any] | None


async def _planner_node(state: GraphState) -> dict[str, Any]:
    """Call the Planner LLM and store the resulting plan in state."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    user_text = last.content if last and hasattr(last, "content") else ""

    try:
        plan = await run_planner(str(user_text))
    except PlannerError as exc:
        return {"error": str(exc)}

    return {
        "plan": [step.model_dump() for step in plan.steps],
        "current_step": 0,
        "iterations": state.get("iterations", 0),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Real agent nodes
# ---------------------------------------------------------------------------


async def _research_node(state: GraphState) -> Any:
    """Run the Research Agent and return Command(goto='supervisor')."""
    from langgraph.types import Command

    from agents.research.nodes import run_research_agent

    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))
    goal = steps[idx].get("goal", "") if 0 <= idx < len(steps) else ""

    try:
        _, observation = await run_research_agent(goal)
    except Exception as exc:
        observation = f"Research failed: {exc}"

    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done"}

    observations = list(state.get("observations") or [])
    observations.append(observation)

    return Command(goto="supervisor", update={"plan": steps, "observations": observations})


# ---------------------------------------------------------------------------
# Stub nodes — replaced by real implementations in T10-T19
# ---------------------------------------------------------------------------


def _stub_agent(name: str, *, goto: str = "supervisor") -> Any:
    """Return a node function that marks the current step as done."""
    from langgraph.types import Command

    def _node(state: GraphState) -> Any:
        idx = state.get("current_step", 0)
        steps = list(state.get("plan", []))
        if 0 <= idx < len(steps):
            steps[idx] = {**steps[idx], "status": "done"}
        return Command(goto=goto, update={"plan": steps})

    _node.__name__ = name
    return _node


def _tool_executor_stub(state: GraphState) -> Any:
    """Stub tool executor — T19 will implement full ToolRegistry dispatch."""
    from langgraph.types import Command

    pending = state.get("pending_tool")
    observations = list(state.get("observations") or [])
    if pending:
        tool_name = pending.get("name", "unknown")
        observations.append(f"[TOOL STUB] {tool_name}: not yet implemented.")
    return Command(goto="supervisor", update={"observations": observations, "pending_tool": None})


def _reflector_stub(_state: GraphState) -> dict[str, Any]:
    """Stub reflector — just ends the graph for now (replaced in T18)."""
    return {}


def _synthesizer_stub(_state: GraphState) -> dict[str, Any]:
    """Stub synthesizer — just ends the graph for now (replaced in T18)."""
    return {}


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,  # type: ignore[type-arg]
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the LangGraph state machine."""
    from agents.hitl import hitl_plan_node, hitl_tool_node
    from agents.policy import policy_guard_node
    from agents.supervisor import supervisor_node

    builder = StateGraph(GraphState)

    # Core nodes
    builder.add_node("planner", _planner_node)
    builder.add_node("hitl_plan", hitl_plan_node)
    builder.add_node("hitl_tool", hitl_tool_node)
    builder.add_node("supervisor", supervisor_node)

    # Policy guard + tool executor (T12 / T19)
    builder.add_node("policy_guard", policy_guard_node)
    builder.add_node("tool_executor", _tool_executor_stub)

    # Research agent (T09)
    builder.add_node("research", _research_node)

    # Agent stubs — video goes direct to supervisor, tool goes through policy_guard
    from agents.image.nodes import run_image_agent

    builder.add_node("image", run_image_agent)
    for agent in ("video",):
        builder.add_node(agent, _stub_agent(agent))
    builder.add_node("tool", _stub_agent("tool", goto="policy_guard"))

    # Reflector / synthesizer stubs (T18)
    builder.add_node("reflector", _reflector_stub)  # type: ignore[arg-type]
    builder.add_node("synthesizer", _synthesizer_stub)  # type: ignore[arg-type]

    # Edges
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "hitl_plan")
    builder.add_edge("hitl_plan", "supervisor")
    builder.add_edge("reflector", END)
    builder.add_edge("synthesizer", END)

    # hitl_tool → tool_executor (approved/edited) or supervisor (rejected)
    builder.add_conditional_edges(
        "hitl_tool",
        lambda state: "tool_executor" if state.get("pending_tool") else "supervisor",
    )

    return builder.compile(checkpointer=checkpointer)


def make_run_id() -> str:
    return str(uuid.uuid4())
