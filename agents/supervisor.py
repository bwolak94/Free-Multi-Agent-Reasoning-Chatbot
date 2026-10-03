from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langgraph.types import Command

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

# Nodes that agent steps map to. Must match node names registered in build_graph().
_AGENT_TO_NODE: dict[str, str] = {
    "research": "research",
    "image": "image",
    "video": "video",
    "tool": "tool",
}


def _all_deps_done(steps: list[dict[str, Any]], deps: list[int]) -> bool:
    """Return True when every dependency step has status 'done'."""
    return all(0 <= i < len(steps) and steps[i].get("status") == "done" for i in deps)


def supervisor_node(state: GraphState) -> Command:  # type: ignore[type-arg]
    """Deterministic router — no LLM call.

    Scans ``state["plan"]`` for the next ``pending`` step whose dependencies
    are all ``done`` and dispatches to the matching agent node via
    ``Command(goto=...)``.

    Routing table
    -------------
    - Pending step found, deps met → ``Command(goto=agent_node)``
    - No pending steps remain     → ``Command(goto="reflector")``
    - All steps done / exhausted  → ``Command(goto="synthesizer")``
    """
    steps: list[dict[str, Any]] = list(state.get("plan", []))

    # Find the next dispatchable step
    for idx, step in enumerate(steps):
        if step.get("status") != "pending":
            continue

        deps: list[int] = step.get("deps", [])
        if not _all_deps_done(steps, deps):
            logger.debug("Supervisor: step %d waiting on deps %s", idx, deps)
            continue

        # Mark step as running
        updated = list(steps)
        updated[idx] = {**step, "status": "running"}

        agent: str = step.get("agent", "tool")
        node = _AGENT_TO_NODE.get(agent, "tool")

        logger.debug("Supervisor: dispatching step %d to node %r", idx, node)
        return Command(
            goto=node,
            update={"plan": updated, "current_step": idx},
        )

    # No dispatchable pending step found
    has_running = any(s.get("status") == "running" for s in steps)
    all_done = all(s.get("status") == "done" for s in steps) and bool(steps)

    if all_done:
        logger.debug("Supervisor: all steps done → synthesizer")
        return Command(goto="synthesizer")

    if not has_running:
        # No step running and none dispatchable → reflect and possibly re-plan
        logger.debug("Supervisor: no pending/running steps → reflector")
        return Command(goto="reflector")

    # Steps still running (shouldn't normally land here, but be safe)
    logger.debug("Supervisor: steps still running → reflector")
    return Command(goto="reflector")
