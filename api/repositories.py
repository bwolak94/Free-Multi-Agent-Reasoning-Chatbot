from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from api.models import Thread, ThreadStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        hitl_config: dict[str, object] | None = None,
        thread_id: str | None = None,
    ) -> Thread:
        now = datetime.now(UTC)
        thread = Thread(
            id=thread_id or str(uuid.uuid4()),
            status=ThreadStatus.idle,
            hitl_config=hitl_config,
            created_at=now,
            updated_at=now,
        )
        self._session.add(thread)
        await self._session.commit()
        await self._session.refresh(thread)
        return thread

    async def get(self, thread_id: str) -> Thread | None:
        result = await self._session.execute(select(Thread).where(Thread.id == thread_id))
        return result.scalar_one_or_none()

    async def update_status(self, thread_id: str, status: ThreadStatus) -> None:
        await self._session.execute(
            update(Thread)
            .where(Thread.id == thread_id)
            .values(status=status, updated_at=datetime.now(UTC))
        )
        await self._session.commit()
