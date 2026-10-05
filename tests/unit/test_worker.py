from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas import ProgressEvent
from api.worker_client import enqueue_job, stream_job_progress
from workers.jobs import BaseWorkerJob, DummyJob

# ---------------------------------------------------------------------------
# BaseWorkerJob.on_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_on_progress_publishes_to_correct_channel() -> None:
    mock_redis = AsyncMock()
    ctx: dict = {"redis": mock_redis}
    job = DummyJob(job_id="abc-123", ctx=ctx)

    await job.on_progress(50, "halfway")

    mock_redis.publish.assert_awaited_once()
    channel, payload = mock_redis.publish.call_args.args
    assert channel == "job:abc-123:progress"

    data = json.loads(payload)
    assert data["type"] == "progress"
    assert data["job_id"] == "abc-123"
    assert data["percent"] == 50
    assert data["message"] == "halfway"


@pytest.mark.unit
async def test_on_progress_default_message_is_empty() -> None:
    mock_redis = AsyncMock()
    ctx: dict = {"redis": mock_redis}
    job = DummyJob(job_id="j1", ctx=ctx)

    await job.on_progress(10)

    _, payload = mock_redis.publish.call_args.args
    assert json.loads(payload)["message"] == ""


# ---------------------------------------------------------------------------
# DummyJob.run — emits 3 progress events + done
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_dummy_job_emits_four_events() -> None:
    mock_redis = AsyncMock()
    ctx: dict = {"redis": mock_redis}
    result = await DummyJob(job_id="job-1", ctx=ctx).run()

    assert result == {"status": "ok"}
    assert mock_redis.publish.await_count == 4  # 25%, 50%, 75%, 100%


@pytest.mark.unit
async def test_dummy_job_last_event_is_100_percent() -> None:
    mock_redis = AsyncMock()
    ctx: dict = {"redis": mock_redis}
    await DummyJob(job_id="job-2", ctx=ctx).run()

    last_call = mock_redis.publish.call_args_list[-1]
    data = json.loads(last_call.args[1])
    assert data["percent"] == 100
    assert data["message"] == "Done"


@pytest.mark.unit
async def test_dummy_job_events_in_ascending_order() -> None:
    mock_redis = AsyncMock()
    ctx: dict = {"redis": mock_redis}
    await DummyJob(job_id="job-3", ctx=ctx).run()

    percents = [json.loads(c.args[1])["percent"] for c in mock_redis.publish.call_args_list]
    assert percents == sorted(percents)
    assert percents[-1] == 100


# ---------------------------------------------------------------------------
# BaseWorkerJob is abstract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_base_worker_job_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseWorkerJob(job_id="x", ctx={"redis": None})  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# stream_job_progress
# ---------------------------------------------------------------------------


def _make_pubsub(messages: list) -> AsyncMock:
    """Build a mock async context-manager pubsub that returns given messages."""
    pubsub = AsyncMock()
    pubsub.__aenter__ = AsyncMock(return_value=pubsub)
    pubsub.__aexit__ = AsyncMock(return_value=False)
    pubsub.subscribe = AsyncMock()
    pubsub.get_message = AsyncMock(side_effect=messages)
    return pubsub


def _progress_msg(job_id: str, percent: int, message: str = "") -> dict:
    return {
        "type": "message",
        "data": ProgressEvent(job_id=job_id, percent=percent, message=message).model_dump_json(),
    }


@pytest.mark.unit
async def test_stream_yields_progress_events() -> None:
    messages = [
        _progress_msg("j1", 50, "half"),
        _progress_msg("j1", 100, "done"),
    ]
    pubsub = _make_pubsub(messages)
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    mock_redis.aclose = AsyncMock()

    events = []
    async for event in stream_job_progress("j1", redis_client=mock_redis, idle_timeout=1.0):
        events.append(event)

    assert len(events) == 2
    assert events[0].percent == 50
    assert events[1].percent == 100


@pytest.mark.unit
async def test_stream_stops_at_100_percent() -> None:
    # 100% is followed by another message that should NOT be yielded
    messages = [
        _progress_msg("j2", 100, "done"),
        _progress_msg("j2", 200, "should-never-yield"),  # unreachable
    ]
    pubsub = _make_pubsub(messages)
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    mock_redis.aclose = AsyncMock()

    events = []
    async for event in stream_job_progress("j2", redis_client=mock_redis, idle_timeout=1.0):
        events.append(event)

    assert len(events) == 1
    assert events[0].percent == 100


@pytest.mark.unit
async def test_stream_exits_on_idle_timeout() -> None:
    # No messages → idle timeout expires
    pubsub = _make_pubsub([None, None])
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    mock_redis.aclose = AsyncMock()

    events = []
    async for event in stream_job_progress(
        "j3", redis_client=mock_redis, poll_interval=0.0, idle_timeout=0.0
    ):
        events.append(event)

    assert events == []


@pytest.mark.unit
async def test_stream_skips_non_message_types() -> None:
    """subscribe/unsubscribe messages (type != 'message') must be ignored."""
    messages = [
        {"type": "subscribe", "data": 1},
        _progress_msg("j4", 100, "done"),
    ]
    pubsub = _make_pubsub(messages)
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    mock_redis.aclose = AsyncMock()

    events = []
    async for event in stream_job_progress("j4", redis_client=mock_redis, idle_timeout=1.0):
        events.append(event)

    assert len(events) == 1


# ---------------------------------------------------------------------------
# enqueue_job
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_enqueue_job_returns_job_id() -> None:
    mock_job = MagicMock()
    mock_job.job_id = "test-job-id-xyz"

    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

    with patch("api.worker_client.get_arq_pool", AsyncMock(return_value=mock_pool)):
        job_id = await enqueue_job("run_dummy_job", job_id="test-job-id-xyz")

    assert job_id == "test-job-id-xyz"
    mock_pool.enqueue_job.assert_awaited_once_with("run_dummy_job", job_id="test-job-id-xyz")


@pytest.mark.unit
async def test_enqueue_job_raises_when_pool_returns_none() -> None:
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value=None)

    with (
        patch("api.worker_client.get_arq_pool", AsyncMock(return_value=mock_pool)),
        pytest.raises(RuntimeError, match="Failed to enqueue"),
    ):
        await enqueue_job("run_dummy_job", job_id="dup")
