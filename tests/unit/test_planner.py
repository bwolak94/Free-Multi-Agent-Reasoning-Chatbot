from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.planner import AgentType, Plan, PlannerError, Step, run_planner


def _make_plan(*agents: AgentType) -> Plan:
    return Plan(
        goal="test goal",
        steps=[Step(agent=a, goal=f"step {i}") for i, a in enumerate(agents)],
        created_at=datetime.now(UTC),
    )


@pytest.mark.unit
async def test_run_planner_returns_plan() -> None:
    expected = _make_plan("research")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=expected)

    with patch("agents.planner.get_llm", return_value=mock_llm):
        result = await run_planner("research topic X")

    assert isinstance(result, Plan)
    assert len(result.steps) == 1
    assert result.steps[0].agent == "research"


@pytest.mark.unit
async def test_run_planner_multi_step() -> None:
    expected = _make_plan("research", "image")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=expected)

    with patch("agents.planner.get_llm", return_value=mock_llm):
        result = await run_planner("research X and generate an image")

    assert len(result.steps) == 2
    assert result.steps[0].agent == "research"
    assert result.steps[1].agent == "image"


@pytest.mark.unit
async def test_run_planner_step_deps() -> None:
    plan = Plan(
        goal="deps test",
        steps=[
            Step(agent="research", goal="step 0", deps=[]),
            Step(agent="image", goal="step 1", deps=[0]),
        ],
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=plan)

    with patch("agents.planner.get_llm", return_value=mock_llm):
        result = await run_planner("research and image")

    assert result.steps[1].deps == [0]


@pytest.mark.unit
async def test_run_planner_retries_on_failure() -> None:
    expected = _make_plan("tool")
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(
        side_effect=[ValueError("bad json"), ValueError("bad json"), expected]
    )
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("agents.planner.get_llm", return_value=mock_llm):
        result = await run_planner("do something", max_retries=3)

    assert mock_structured.ainvoke.call_count == 3
    assert result.steps[0].agent == "tool"


@pytest.mark.unit
async def test_run_planner_raises_after_max_retries() -> None:
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=ValueError("always fails")
    )

    with (
        patch("agents.planner.get_llm", return_value=mock_llm),
        pytest.raises(PlannerError, match="Planner failed after 3 attempts"),
    ):
        await run_planner("fail", max_retries=3)


@pytest.mark.unit
async def test_step_defaults() -> None:
    step = Step(agent="research", goal="find something")
    assert step.status == "pending"
    assert step.deps == []
    assert step.inputs == {}


@pytest.mark.unit
async def test_plan_model_dump_contains_steps() -> None:
    plan = _make_plan("research", "tool")
    dumped: dict[str, Any] = plan.model_dump()
    assert len(dumped["steps"]) == 2
    assert dumped["steps"][0]["agent"] == "research"


@pytest.mark.unit
async def test_step_all_agent_types() -> None:
    for agent in ("research", "image", "video", "tool"):
        step = Step(agent=agent, goal="test")  # type: ignore[arg-type]
        assert step.agent == agent
