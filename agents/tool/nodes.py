from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from api.llm import get_llm
from tools.base import ToolNotFoundError, get_registry

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

_SELECT_SYSTEM = """\
You are a tool dispatcher. Given a goal and a list of available tools, select
the single best tool and provide the exact arguments required.

Available tools (name | description | input schema):
{tool_list}

Respond with valid JSON matching the output schema exactly — no prose.
"""


class ToolSelection(BaseModel):
    name: str
    args: dict[str, Any]
    rationale: str


async def select_tool_node(state: GraphState) -> Any:
    """LangGraph node — LLM selects a tool from ToolRegistry for the current step.

    Sets ``pending_tool`` in state and routes to ``policy_guard``.
    On failure (no tools registered, LLM error) routes to ``supervisor``
    with an ``ErrorObservation``.
    """
    from langgraph.types import Command

    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))
    step = steps[idx] if 0 <= idx < len(steps) else {}
    goal: str = step.get("goal", "")

    observations = list(state.get("observations") or [])

    registry = get_registry()
    tool_descriptors = registry.list_all()

    if not tool_descriptors:
        observations.append(f"[TOOL ERROR] No tools registered — cannot execute: {goal}")
        if 0 <= idx < len(steps):
            steps[idx] = {**steps[idx], "status": "done"}
        return Command(goto="supervisor", update={"plan": steps, "observations": observations})

    tool_list = "\n".join(
        f"- {t.name} | {t.description} | {t.input_schema}" for t in tool_descriptors
    )

    llm = get_llm("fast")
    structured_llm = llm.with_structured_output(ToolSelection)

    messages = [
        SystemMessage(content=_SELECT_SYSTEM.format(tool_list=tool_list)),
        {"role": "user", "content": f"Goal: {goal}"},
    ]

    try:
        selection: ToolSelection = await structured_llm.ainvoke(messages)
        logger.debug(
            "select_tool: step=%d tool=%r rationale=%s",
            idx,
            selection.name,
            selection.rationale,
        )
        pending_tool = {"name": selection.name, "args": selection.args}
        return Command(goto="policy_guard", update={"pending_tool": pending_tool})

    except Exception as exc:
        logger.warning("select_tool failed for step %d: %s", idx, exc)
        observations.append(f"[TOOL ERROR] Tool selection failed: {exc}")
        if 0 <= idx < len(steps):
            steps[idx] = {**steps[idx], "status": "done"}
        return Command(goto="supervisor", update={"plan": steps, "observations": observations})


async def execute_tool_node(state: GraphState) -> Any:
    """LangGraph node — executes ``pending_tool`` via ToolRegistry.

    Applies per-tool timeout. Always routes to ``supervisor``.
    Produces either a normal observation or an ``ErrorObservation``.
    """
    from langgraph.types import Command

    pending: dict[str, Any] = state.get("pending_tool") or {}
    observations = list(state.get("observations") or [])
    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))

    if not pending:
        return Command(
            goto="supervisor",
            update={"observations": observations, "pending_tool": None},
        )

    tool_name: str = pending.get("name", "")
    args: dict[str, Any] = pending.get("args", {})
    start = time.monotonic()

    try:
        registered_tool = get_registry().get(tool_name)
        timeout: int = getattr(registered_tool, "_timeout", 30)

        result = await asyncio.wait_for(registered_tool(**args), timeout=timeout)
        duration = time.monotonic() - start

        logger.info(
            "tool_execute: tool=%r args=%r duration=%.2fs",
            tool_name,
            args,
            duration,
        )
        observations.append(f"[TOOL {tool_name}] {result}")

    except TimeoutError:
        duration = time.monotonic() - start
        logger.warning("tool_execute: timeout tool=%r after %.1fs", tool_name, duration)
        observations.append(f"[TOOL ERROR] {tool_name} timed out after {duration:.1f}s — skipping.")

    except ToolNotFoundError as exc:
        logger.warning("tool_execute: not found tool=%r: %s", tool_name, exc)
        observations.append(f"[TOOL ERROR] Tool not found: {tool_name}")

    except Exception as exc:
        duration = time.monotonic() - start
        logger.warning("tool_execute: error tool=%r: %s", tool_name, exc)
        observations.append(f"[TOOL ERROR] {tool_name} failed: {exc}")

    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done"}

    return Command(
        goto="supervisor",
        update={"plan": steps, "observations": observations, "pending_tool": None},
    )
