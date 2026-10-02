import pytest

from api.schemas import (
    ArtifactEvent,
    DoneEvent,
    ErrorEvent,
    InterruptEvent,
    ProgressEvent,
    StepEvent,
    TokenEvent,
)


@pytest.mark.unit
def test_token_event() -> None:
    e = TokenEvent(delta="hello")
    assert e.type == "token"
    assert e.delta == "hello"


@pytest.mark.unit
def test_step_event() -> None:
    e = StepEvent(node="planner", status="done", step_index=0)
    assert e.type == "step"
    assert e.step_index == 0


@pytest.mark.unit
def test_interrupt_event() -> None:
    e = InterruptEvent(subject="plan", data={"steps": []})
    assert e.type == "interrupt"
    assert e.subject == "plan"


@pytest.mark.unit
def test_artifact_event() -> None:
    e = ArtifactEvent(artifact_id="abc", url="https://example.com/img.png", artifact_type="image")
    assert e.type == "artifact"


@pytest.mark.unit
def test_progress_event() -> None:
    e = ProgressEvent(job_id="j1", percent=50, message="half done")
    assert e.type == "progress"
    assert e.percent == 50


@pytest.mark.unit
def test_done_event() -> None:
    e = DoneEvent(thread_id="t1", run_id="r1")
    assert e.type == "done"


@pytest.mark.unit
def test_error_event() -> None:
    e = ErrorEvent(code="ERR_TIMEOUT", message="request timed out")
    assert e.type == "error"
