from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.models import Base, ThreadStatus
from api.repositories import ThreadRepository


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.unit
async def test_create_thread(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    thread = await repo.create()
    assert thread.id is not None
    assert thread.status == ThreadStatus.idle


@pytest.mark.unit
async def test_create_thread_with_custom_id(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    thread = await repo.create(thread_id="my-thread")
    assert thread.id == "my-thread"


@pytest.mark.unit
async def test_create_thread_with_hitl_config(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    config = {"approve_plan": True, "review_output": False}
    thread = await repo.create(hitl_config=config)
    assert thread.hitl_config == config


@pytest.mark.unit
async def test_get_thread(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    created = await repo.create(thread_id="abc")
    fetched = await repo.get("abc")
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.unit
async def test_get_thread_not_found(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    result = await repo.get("does-not-exist")
    assert result is None


@pytest.mark.unit
async def test_update_status(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    await repo.create(thread_id="t1")
    await repo.update_status("t1", ThreadStatus.running)
    thread = await repo.get("t1")
    assert thread is not None
    assert thread.status == ThreadStatus.running


@pytest.mark.unit
async def test_update_status_waiting_hitl(session: AsyncSession) -> None:
    repo = ThreadRepository(session)
    await repo.create(thread_id="t2")
    await repo.update_status("t2", ThreadStatus.waiting_hitl)
    thread = await repo.get("t2")
    assert thread is not None
    assert thread.status == ThreadStatus.waiting_hitl
