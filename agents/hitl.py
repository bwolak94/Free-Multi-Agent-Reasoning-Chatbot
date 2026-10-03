from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)


def hitl_plan_node(state: GraphState) -> dict[str, Any]:
    """HITL gate #1 — plan approval.

    If ``hitl_config.approve_plan`` is True, pauses the graph via
    ``interrupt()`` and waits for the client to call ``POST /threads/{id}/resume``.

    Resume payload
    --------------
    ``{"action": "approve"}``            → continue unchanged
    ``{"action": "edit", "plan": [...]}`` → replace plan with edited version
    ``{"action": "reject", "reason": ""}`` → abort with error message
    """
    hitl_cfg: dict[str, Any] = state.get("hitl_config") or {}
    if not hitl_cfg.get("approve_plan"):
        return {}  # gate is off — pass through

    plan = state.get("plan", [])
    resume: dict[str, Any] = interrupt({"subject": "plan", "data": plan})

    action = resume.get("action", "approve")
    logger.debug("HITL plan resume: action=%s", action)

    if action == "edit":
        return {"plan": resume.get("plan", plan)}

    if action == "reject":
        return {"error": resume.get("reason", "Plan rejected by user"), "plan": []}

    # action == "approve" (or anything else) → continue unchanged
    return {}


def hitl_tool_node(state: GraphState) -> dict[str, Any]:
    """HITL gate #2 — tool-call approval.

    Called by the Policy Guard (T12) before high-risk tool execution.
    The tool metadata is stored in ``state["pending_tool"]``.

    Resume payload
    --------------
    ``{"action": "approve"}``                      → execute tool unchanged
    ``{"action": "edit", "tool_args": {...}}``     → replace tool args
    ``{"action": "reject", "reason": ""}``         → add rejection observation
    """
    pending: dict[str, Any] = state.get("pending_tool") or {}
    tool_name = pending.get("name", "unknown")
    tool_args = pending.get("args", {})

    resume: dict[str, Any] = interrupt(
        {"subject": "tool", "data": {"tool_name": tool_name, "args": tool_args}}
    )

    action = resume.get("action", "approve")
    logger.debug("HITL tool resume: action=%s tool=%s", action, tool_name)

    if action == "edit":
        updated = {**pending, "args": resume.get("tool_args", tool_args)}
        return {"pending_tool": updated}

    if action == "reject":
        reason = resume.get("reason", f"Tool {tool_name!r} rejected by user")
        observations: list[str] = list(state.get("observations") or [])
        observations.append(f"[REJECTED] {reason}")
        return {"observations": observations, "pending_tool": None}

    # approve
    return {}
