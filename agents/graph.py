from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

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
    """

    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[dict[str, Any]]
    current_step: int
    artifacts: list[dict[str, Any]]
    observations: list[str]
    iterations: int
    hitl_config: dict[str, Any] | None


def _router_node(state: GraphState) -> dict[str, Any]:
    """Trivial echo router — replaced in T06 by the real Planner."""
    last = state.get("messages", [])
    text = last[-1].content if last else ""
    echo = HumanMessage(content=f"[echo] {text}", name="router")
    return {"messages": [echo]}


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,  # type: ignore[type-arg]
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the LangGraph state machine."""
    builder = StateGraph(GraphState)
    builder.add_node("router", _router_node)
    builder.add_edge(START, "router")
    builder.add_edge("router", END)
    return builder.compile(checkpointer=checkpointer)


def make_run_id() -> str:
    return str(uuid.uuid4())
