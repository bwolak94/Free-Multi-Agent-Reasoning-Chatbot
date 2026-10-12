"""FakeLLM helpers for the eval suite — no real API calls."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from agents.planner import Plan, Step


def make_plan(*agents: str, goal: str = "test goal") -> Plan:
    """Return a Plan with one Step per agent string."""
    return Plan(
        goal=goal,
        steps=[Step(agent=a, goal=f"step: {a}") for a in agents],  # type: ignore[arg-type]
        created_at=datetime.now(UTC),
    )


def fake_planner_llm(plan: Plan) -> MagicMock:
    """Mock LLM whose with_structured_output().ainvoke() returns *plan*."""
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=plan)
    return llm


def fake_fast_llm(answer: str = "Synthesized answer.") -> MagicMock:
    """Mock LLM whose ainvoke() returns an AIMessage with *answer*."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=answer))
    # with_structured_output used by select_tool_node — return a sensible default
    from agents.tool.nodes import ToolSelection

    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=ToolSelection(name="web.search", args={"query": "test"}, rationale="eval")
    )
    return llm


def fake_research_result(observation: str = "Research observation") -> AsyncMock:
    """AsyncMock for run_research_agent returning (messages, observation)."""
    return AsyncMock(return_value=("", observation))


async def fake_image_node(state: Any) -> Any:
    """Drop-in replacement for run_image_agent — marks step done, adds artifact."""
    from langgraph.types import Command

    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))
    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done"}

    obs = list(state.get("observations") or [])
    obs.append("Image generated: http://fake/image.png")

    arts = list(state.get("artifacts") or [])
    arts.append({"artifact_type": "image", "url": "http://fake/image.png"})

    return Command(
        goto="supervisor", update={"plan": steps, "observations": obs, "artifacts": arts}
    )
