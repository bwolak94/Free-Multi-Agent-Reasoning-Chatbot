from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from agents.graph import GraphState, build_graph
from agents.planner import Plan, Step


def _mock_plan() -> Plan:
    return Plan(
        goal="test",
        steps=[Step(agent="research", goal="find info")],
        created_at=datetime.now(UTC),
    )


@pytest.mark.unit
async def test_build_graph_returns_compiled_graph() -> None:
    graph = build_graph()
    assert graph is not None


@pytest.mark.unit
async def test_graph_invoke_runs_planner() -> None:
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=_mock_plan())

    with patch("agents.planner.get_llm", return_value=mock_llm):
        graph = build_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="research topic X")]},
            config={"configurable": {"thread_id": "test-1"}},
        )

    assert "plan" in result
    assert len(result["plan"]) == 1
    assert result["plan"][0]["agent"] == "research"


@pytest.mark.unit
async def test_graph_state_fields() -> None:
    annotations = GraphState.__annotations__
    expected = {
        "messages",
        "plan",
        "current_step",
        "artifacts",
        "observations",
        "iterations",
        "hitl_config",
    }
    assert expected.issubset(set(annotations.keys()))


@pytest.mark.unit
async def test_graph_streams_events() -> None:
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=_mock_plan())

    with patch("agents.planner.get_llm", return_value=mock_llm):
        graph = build_graph()
        events = []
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content="hi")]},
            config={"configurable": {"thread_id": "test-2"}},
            version="v2",
        ):
            events.append(event)

    assert len(events) > 0


@pytest.mark.unit
async def test_graph_planner_error_sets_error_field() -> None:
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=ValueError("always fails")
    )

    with patch("agents.planner.get_llm", return_value=mock_llm):
        graph = build_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="bad request")]},
            config={"configurable": {"thread_id": "test-err"}},
        )

    assert result.get("error") is not None


@pytest.mark.unit
async def test_graph_with_checkpointer_persists_state() -> None:
    from api.checkpointer import get_checkpointer
    from api.settings import settings

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=_mock_plan())

    settings.use_sqlite = True
    with patch("agents.planner.get_llm", return_value=mock_llm):
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": "persist-test"}}
            await graph.ainvoke(
                {"messages": [HumanMessage(content="remember me")]},
                config=config,
            )
            state = await graph.aget_state(config)
            assert state is not None
            assert len(state.values.get("messages", [])) > 0
    settings.use_sqlite = False
