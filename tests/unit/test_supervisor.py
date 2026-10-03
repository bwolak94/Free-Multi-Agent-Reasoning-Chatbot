from __future__ import annotations

import pytest
from langgraph.types import Command

from agents.graph import GraphState
from agents.supervisor import supervisor_node


def _make_state(steps: list[dict], current_step: int = 0) -> GraphState:
    return GraphState(plan=steps, current_step=current_step)  # type: ignore[call-arg]


def _step(agent: str, status: str = "pending", deps: list[int] | None = None) -> dict:
    return {
        "agent": agent,
        "goal": f"{agent} goal",
        "status": status,
        "deps": deps or [],
        "inputs": {},
    }


@pytest.mark.unit
def test_routes_to_research() -> None:
    state = _make_state([_step("research")])
    cmd = supervisor_node(state)
    assert isinstance(cmd, Command)
    assert cmd.goto == "research"


@pytest.mark.unit
def test_routes_to_image() -> None:
    state = _make_state([_step("image")])
    cmd = supervisor_node(state)
    assert cmd.goto == "image"


@pytest.mark.unit
def test_routes_to_video() -> None:
    state = _make_state([_step("video")])
    cmd = supervisor_node(state)
    assert cmd.goto == "video"


@pytest.mark.unit
def test_routes_to_tool() -> None:
    state = _make_state([_step("tool")])
    cmd = supervisor_node(state)
    assert cmd.goto == "tool"


@pytest.mark.unit
def test_unknown_agent_falls_back_to_tool() -> None:
    state = _make_state([_step("unknown_agent")])
    cmd = supervisor_node(state)
    assert cmd.goto == "tool"


@pytest.mark.unit
def test_marks_step_as_running_in_update() -> None:
    state = _make_state([_step("research")])
    cmd = supervisor_node(state)
    updated_steps = cmd.update["plan"]  # type: ignore[index]
    assert updated_steps[0]["status"] == "running"


@pytest.mark.unit
def test_updates_current_step_index() -> None:
    steps = [_step("research", "done"), _step("image")]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    assert cmd.update["current_step"] == 1  # type: ignore[index]


@pytest.mark.unit
def test_deps_not_met_skips_step() -> None:
    # step 1 depends on step 0 which is still pending
    steps = [_step("research", "pending"), _step("image", "pending", deps=[0])]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    # Should dispatch step 0 first (no deps), not step 1
    assert cmd.goto == "research"
    assert cmd.update["current_step"] == 0  # type: ignore[index]


@pytest.mark.unit
def test_deps_met_dispatches_dependent_step() -> None:
    steps = [_step("research", "done"), _step("image", "pending", deps=[0])]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    assert cmd.goto == "image"
    assert cmd.update["current_step"] == 1  # type: ignore[index]


@pytest.mark.unit
def test_all_done_goes_to_synthesizer() -> None:
    steps = [_step("research", "done"), _step("image", "done")]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    assert cmd.goto == "synthesizer"


@pytest.mark.unit
def test_empty_plan_goes_to_reflector() -> None:
    state = _make_state([])
    cmd = supervisor_node(state)
    assert cmd.goto == "reflector"


@pytest.mark.unit
def test_no_dispatchable_step_goes_to_reflector() -> None:
    # Step 1 can't run (dep 0 is pending), step 0 is running → no pending+dispatchable
    steps = [_step("research", "running"), _step("image", "pending", deps=[0])]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    assert cmd.goto == "reflector"


@pytest.mark.unit
def test_skips_non_pending_steps() -> None:
    steps = [
        _step("research", "done"),
        _step("image", "error"),
        _step("tool", "pending"),
    ]
    state = _make_state(steps)
    cmd = supervisor_node(state)
    assert cmd.goto == "tool"
    assert cmd.update["current_step"] == 2  # type: ignore[index]
