from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agents.graph import GraphState, build_graph


@pytest.mark.unit
async def test_build_graph_returns_compiled_graph() -> None:
    graph = build_graph()
    assert graph is not None


@pytest.mark.unit
async def test_graph_invoke_echo() -> None:
    graph = build_graph()
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")]},
        config={"configurable": {"thread_id": "test-1"}},
    )
    messages = result["messages"]
    assert len(messages) == 2
    assert "[echo]" in messages[-1].content


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
async def test_graph_with_checkpointer_persists_state() -> None:
    from api.checkpointer import get_checkpointer
    from api.settings import settings

    settings.use_sqlite = True
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
