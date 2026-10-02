from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.database import get_session
from api.main import app
from api.models import Base, ThreadStatus
from api.settings import settings


@pytest.fixture(autouse=True)
def _force_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_sqlite", True)


@pytest.fixture
async def client() -> AsyncClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session() -> AsyncSession:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.unit
async def test_create_thread(client: AsyncClient) -> None:
    resp = await client.post("/threads", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data


@pytest.mark.unit
async def test_create_thread_with_custom_id(client: AsyncClient) -> None:
    resp = await client.post("/threads", json={"thread_id": "my-id"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "my-id"


@pytest.mark.unit
async def test_get_thread(client: AsyncClient) -> None:
    create_resp = await client.post("/threads", json={})
    thread_id = create_resp.json()["id"]
    resp = await client.get(f"/threads/{thread_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == thread_id
    assert data["status"] == ThreadStatus.idle.value


@pytest.mark.unit
async def test_get_thread_not_found(client: AsyncClient) -> None:
    resp = await client.get("/threads/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.unit
async def test_run_streams_done_event(client: AsyncClient) -> None:
    create_resp = await client.post("/threads", json={})
    thread_id = create_resp.json()["id"]

    resp = await client.post(
        f"/threads/{thread_id}/runs",
        json={"message": "hello"},
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "done" in body
    assert thread_id in body


@pytest.mark.unit
async def test_run_not_found(client: AsyncClient) -> None:
    resp = await client.post("/threads/no-such-thread/runs", json={"message": "hi"})
    assert resp.status_code == 404
