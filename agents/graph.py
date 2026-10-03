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


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,  # type: ignore[type-arg]
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the LangGraph state machine."""
    builder = StateGraph(GraphState)
    builder.add_node("planner", _planner_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", END)
    return builder.compile(checkpointer=checkpointer)


def make_run_id() -> str:
    return str(uuid.uuid4())
