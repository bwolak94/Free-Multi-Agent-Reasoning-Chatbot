from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.database import get_session
from api.main import app
from api.models import Base
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
async def test_resume_thread_not_found(client: AsyncClient) -> None:
    resp = await client.post("/threads/no-such/resume", json={"action": "approve"})
    assert resp.status_code == 404


@pytest.mark.unit
async def test_resume_thread_not_waiting(client: AsyncClient) -> None:
    create_resp = await client.post("/threads", json={})
    thread_id = create_resp.json()["id"]
    # Thread is idle, not waiting_hitl
    resp = await client.post(f"/threads/{thread_id}/resume", json={"action": "approve"})
    assert resp.status_code == 409


@pytest.mark.unit
async def test_resume_request_schema_approve() -> None:
    from api.routers.threads import ResumeRequest

    req = ResumeRequest(action="approve")
    assert req.action == "approve"
    assert req.plan is None
    assert req.reason is None


@pytest.mark.unit
async def test_resume_request_schema_edit_with_plan() -> None:
    from api.routers.threads import ResumeRequest

    new_plan = [{"agent": "research", "goal": "find stuff"}]
    req = ResumeRequest(action="edit", plan=new_plan)
    assert req.plan == new_plan


@pytest.mark.unit
async def test_resume_request_schema_reject_with_reason() -> None:
    from api.routers.threads import ResumeRequest

    req = ResumeRequest(action="reject", reason="Not safe")
    assert req.reason == "Not safe"
