"""
T21 — Eval suite: 5 canonical scenarios + HITL interrupt/resume end-to-end.

All tests use FakeLLM helpers — no real API calls, no network I/O.
Run via:  uv run pytest tests/ -m eval
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graph import build_graph
from tests.eval.fake_llm import (
    fake_fast_llm,
    fake_image_node,
    fake_planner_llm,
    fake_research_result,
    make_plan,
)

# ---------------------------------------------------------------------------
# Scenario 1 — Simple single-step plan runs end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.eval
async def test_simple_single_step_plan() -> None:
    """Planner → research → synthesizer completes without HITL."""
    plan = make_plan("research")

    with (
        patch("agents.planner.get_llm", return_value=fake_planner_llm(plan)),
        patch("agents.synthesizer.get_llm", return_value=fake_fast_llm("Here is your answer.")),
        patch(
            "agents.research.nodes.run_research_agent", new=fake_research_result("Research result")
        ),
    ):
        graph = build_graph()
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content="Tell me about AI")]},
            config={"configurable": {"thread_id": "eval-1"}},
        )

    assert state["plan"][0]["status"] == "done"
    assert any(isinstance(m, AIMessage) for m in state["messages"])


# ---------------------------------------------------------------------------
# Scenario 2 — Research task with HITL #1 approve
# ---------------------------------------------------------------------------


@pytest.mark.eval
async def test_research_with_hitl_plan_approve() -> None:
    """HITL gates the plan; user approves; full pipeline runs."""
    plan = make_plan("research")

    with (
        patch("agents.planner.get_llm", return_value=fake_planner_llm(plan)),
        patch("agents.synthesizer.get_llm", return_value=fake_fast_llm("Answer after HITL.")),
        patch("agents.research.nodes.run_research_agent", new=fake_research_result("HITL obs")),
        patch("agents.hitl.interrupt", return_value={"action": "approve"}),
    ):
        graph = build_graph()
        state = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Research quantum computing")],
                "hitl_config": {"approve_plan": True},
            },
            config={"configurable": {"thread_id": "eval-2"}},
        )

    assert state["plan"][0]["status"] == "done"
    assert any("HITL obs" in obs for obs in state.get("observations", []))


# ---------------------------------------------------------------------------
# Scenario 3 — Research + image task end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.eval
async def test_research_and_image_end_to_end() -> None:
    """Two-step plan: research then image — both complete, artifact collected."""
    plan = make_plan("research", "image")

    with (
        patch("agents.planner.get_llm", return_value=fake_planner_llm(plan)),
        patch("agents.synthesizer.get_llm", return_value=fake_fast_llm("Combined answer.")),
        patch(
            "agents.research.nodes.run_research_agent", new=fake_research_result("Background done")
        ),
        patch("agents.image.nodes.run_image_agent", new=fake_image_node),
    ):
        graph = build_graph()
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content="Create an infographic about climate")]},
            config={"configurable": {"thread_id": "eval-3"}},
        )

    assert all(s["status"] == "done" for s in state["plan"])
    assert len(state.get("artifacts", [])) == 1
    assert state["artifacts"][0]["artifact_type"] == "image"
    assert len(state.get("observations", [])) == 2  # research + image


# ---------------------------------------------------------------------------
# Scenario 4 — Policy rule: deny blocked domain
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_policy_deny_blocked_domain() -> None:
    """PolicyEngine denies tool calls matching a block rule; allows others."""
    from agents.policy import PolicyCondition, PolicyEngine, PolicyRule

    engine = PolicyEngine.__new__(PolicyEngine)
    engine._prompt_rules = []
    engine._policy_rules = [
        PolicyRule(
            id="block-malicious",
            when=PolicyCondition(tool="web.fetch", arg="url", matches=r"blocked\.com"),
            action="deny",
        )
    ]

    denied = engine.evaluate_tool_call("web.fetch", {"url": "https://blocked.com/data"})
    assert denied.action == "deny"
    assert denied.rule_id == "block-malicious"

    allowed = engine.evaluate_tool_call("web.fetch", {"url": "https://safe.org/data"})
    assert allowed.action == "allow"


# ---------------------------------------------------------------------------
# Scenario 5 — Tool call with HITL #2 rejection
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_tool_hitl_rejection_clears_pending_tool() -> None:
    """HITL #2 rejects a pending tool call; observation recorded, tool cleared."""
    from agents.hitl import hitl_tool_node

    state = {
        "pending_tool": {"name": "web.fetch", "args": {"url": "https://example.com"}},
        "observations": ["previous obs"],
    }

    with patch("agents.hitl.interrupt", return_value={"action": "reject", "reason": "not allowed"}):
        result = hitl_tool_node(state)  # type: ignore[arg-type]

    assert result["pending_tool"] is None
    assert any("not allowed" in obs for obs in result["observations"])
    assert len(result["observations"]) == 2  # previous + new rejection obs


# ---------------------------------------------------------------------------
# Scenario 6 — HITL interrupt + resume end-to-end (in-memory SQLite graph)
# ---------------------------------------------------------------------------


@pytest.mark.eval
async def test_hitl_plan_interrupt_and_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Graph pauses at hitl_plan interrupt, then resumes on approve and completes."""
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import Command

    from api.checkpointer import get_checkpointer
    from api.settings import settings

    plan = make_plan("research")
    monkeypatch.setattr(settings, "use_sqlite", True)

    thread_id = "eval-hitl-resume"
    config = RunnableConfig(configurable={"thread_id": thread_id})

    with (
        patch("agents.planner.get_llm", return_value=fake_planner_llm(plan)),
        patch(
            "agents.synthesizer.get_llm", return_value=fake_fast_llm("Final answer after resume.")
        ),
        patch("agents.research.nodes.run_research_agent", new=fake_research_result("Resumed obs")),
    ):
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)

            # First run — expected to pause at hitl_plan
            await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Research topic Y")],
                    "hitl_config": {"approve_plan": True},
                },
                config=config,
            )

            graph_state = await graph.aget_state(config)
            pending = [
                intr for task in (graph_state.tasks or []) for intr in (task.interrupts or [])
            ]
            assert len(pending) > 0, "Expected a HITL interrupt in graph state"

            # Resume with approve
            final = await graph.ainvoke(
                Command(resume={"action": "approve"}),
                config=config,
            )

    assert "plan" in final
    assert final["plan"][0]["status"] == "done"
    assert any(isinstance(m, AIMessage) for m in final["messages"])
