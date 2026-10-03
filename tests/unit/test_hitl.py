from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.graph import GraphState
from agents.hitl import hitl_plan_node, hitl_tool_node


def _state(**kwargs: object) -> GraphState:
    return GraphState(**kwargs)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# hitl_plan_node
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hitl_plan_passthrough_when_disabled() -> None:
    state = _state(hitl_config={"approve_plan": False}, plan=[{"agent": "research"}])
    result = hitl_plan_node(state)
    assert result == {}


@pytest.mark.unit
def test_hitl_plan_passthrough_when_no_config() -> None:
    state = _state(hitl_config=None, plan=[])
    result = hitl_plan_node(state)
    assert result == {}


@pytest.mark.unit
def test_hitl_plan_approve_continues_unchanged() -> None:
    state = _state(hitl_config={"approve_plan": True}, plan=[{"agent": "research"}])
    with patch("agents.hitl.interrupt", return_value={"action": "approve"}):
        result = hitl_plan_node(state)
    assert result == {}


@pytest.mark.unit
def test_hitl_plan_edit_replaces_plan() -> None:
    new_plan = [{"agent": "tool", "goal": "edited"}]
    state = _state(hitl_config={"approve_plan": True}, plan=[{"agent": "research"}])
    with patch("agents.hitl.interrupt", return_value={"action": "edit", "plan": new_plan}):
        result = hitl_plan_node(state)
    assert result["plan"] == new_plan


@pytest.mark.unit
def test_hitl_plan_reject_sets_error_and_clears_plan() -> None:
    state = _state(hitl_config={"approve_plan": True}, plan=[{"agent": "research"}])
    with patch("agents.hitl.interrupt", return_value={"action": "reject", "reason": "No thanks"}):
        result = hitl_plan_node(state)
    assert result["error"] == "No thanks"
    assert result["plan"] == []


@pytest.mark.unit
def test_hitl_plan_reject_default_reason() -> None:
    state = _state(hitl_config={"approve_plan": True}, plan=[])
    with patch("agents.hitl.interrupt", return_value={"action": "reject"}):
        result = hitl_plan_node(state)
    assert "rejected" in result["error"].lower()


@pytest.mark.unit
def test_hitl_plan_interrupt_called_with_correct_subject() -> None:
    plan = [{"agent": "research", "goal": "find stuff"}]
    state = _state(hitl_config={"approve_plan": True}, plan=plan)
    with patch("agents.hitl.interrupt", return_value={"action": "approve"}) as mock_intr:
        hitl_plan_node(state)
    call_arg = mock_intr.call_args[0][0]
    assert call_arg["subject"] == "plan"
    assert call_arg["data"] == plan


# ---------------------------------------------------------------------------
# hitl_tool_node
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hitl_tool_approve_returns_empty() -> None:
    state = _state(pending_tool={"name": "web.search", "args": {"query": "test"}})
    with patch("agents.hitl.interrupt", return_value={"action": "approve"}):
        result = hitl_tool_node(state)
    assert result == {}


@pytest.mark.unit
def test_hitl_tool_edit_updates_args() -> None:
    state = _state(pending_tool={"name": "web.search", "args": {"query": "old"}})
    new_args = {"query": "new"}
    with patch("agents.hitl.interrupt", return_value={"action": "edit", "tool_args": new_args}):
        result = hitl_tool_node(state)
    assert result["pending_tool"]["args"] == new_args


@pytest.mark.unit
def test_hitl_tool_reject_adds_observation() -> None:
    state = _state(
        pending_tool={"name": "web.search", "args": {}},
        observations=["prev obs"],
    )
    with patch("agents.hitl.interrupt", return_value={"action": "reject", "reason": "too risky"}):
        result = hitl_tool_node(state)
    assert result["pending_tool"] is None
    assert any("too risky" in obs for obs in result["observations"])


@pytest.mark.unit
def test_hitl_tool_interrupt_called_with_correct_subject() -> None:
    state = _state(pending_tool={"name": "video.generate", "args": {"prompt": "x"}})
    with patch("agents.hitl.interrupt", return_value={"action": "approve"}) as mock_intr:
        hitl_tool_node(state)
    call_arg = mock_intr.call_args[0][0]
    assert call_arg["subject"] == "tool"
    assert call_arg["data"]["tool_name"] == "video.generate"
