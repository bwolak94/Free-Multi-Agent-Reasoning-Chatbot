import json

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.unit
async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.unit
async def test_stream_test_content_type() -> None:
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        client.stream("GET", "/threads/t1/stream-test") as response,
    ):
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.unit
async def test_stream_test_events() -> None:
    events: list[dict[str, str]] = []

    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        client.stream("GET", "/threads/t1/stream-test") as response,
    ):
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                payload = line.removeprefix("data:").strip()
                if payload:
                    events.append(json.loads(payload))

    types = [e["type"] for e in events]
    assert "token" in types
    assert types[-1] == "done"
    assert sum(1 for t in types if t == "token") == 5


@pytest.mark.unit
async def test_stream_test_done_has_thread_id() -> None:
    done_events: list[dict[str, str]] = []

    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        client.stream("GET", "/threads/my-thread/stream-test") as response,
    ):
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                payload = line.removeprefix("data:").strip()
                if payload:
                    data = json.loads(payload)
                    if data.get("type") == "done":
                        done_events.append(data)

    assert len(done_events) == 1
    assert done_events[0]["thread_id"] == "my-thread"
