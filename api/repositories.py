from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import aioboto3
from sqlalchemy import select, update

from api.models import Artifact, Thread, ThreadStatus, User
from api.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str, username: str, hashed_password: str) -> User:
        now = datetime.now(UTC)
        user = User(
            id=user_id,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            created_at=now,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


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


class ArtifactRepository:
    """Saves and retrieves artifacts via Cloudflare R2 (or local FS in dev mode)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save(
        self,
        data: bytes,
        *,
        artifact_type: str,
        content_type: str,
        filename: str,
    ) -> Artifact:
        artifact_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=settings.artifact_ttl_days)
        r2_key = self._build_key(artifact_id, filename, now)

        if settings.use_local_fs:
            await self._save_local(r2_key, data)
        else:
            await self._save_r2(r2_key, data, content_type)

        artifact = Artifact(
            id=artifact_id,
            r2_key=r2_key,
            artifact_type=artifact_type,
            content_type=content_type,
            created_at=now,
            expires_at=expires_at,
        )
        self._session.add(artifact)
        await self._session.commit()
        await self._session.refresh(artifact)
        return artifact

    async def get(self, artifact_id: str) -> Artifact | None:
        result = await self._session.execute(select(Artifact).where(Artifact.id == artifact_id))
        return result.scalar_one_or_none()

    async def presigned_url(self, artifact_id: str, expires: int = 3600) -> str | None:
        artifact = await self.get(artifact_id)
        if artifact is None:
            return None

        if settings.use_local_fs:
            return f"/artifacts/{artifact_id}/download"

        boto_session = aioboto3.Session(
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )
        async with boto_session.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            region_name="auto",
        ) as client:
            url: str = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.r2_bucket, "Key": artifact.r2_key},
                ExpiresIn=expires,
            )
        return url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_key(artifact_id: str, filename: str, now: datetime) -> str:
        return f"artifacts/{now.year}/{now.month:02d}/{artifact_id}/{filename}"

    @staticmethod
    async def _save_local(r2_key: str, data: bytes) -> None:
        path = Path(settings.artifacts_local_path) / r2_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    async def _save_r2(r2_key: str, data: bytes, content_type: str) -> None:
        boto_session = aioboto3.Session(
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )
        async with boto_session.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            region_name="auto",
        ) as client:
            await client.put_object(
                Bucket=settings.r2_bucket,
                Key=r2_key,
                Body=data,
                ContentType=content_type,
            )


class UserThreadRepository:
    """Thread queries scoped to an authenticated user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Thread]:
        from sqlalchemy import select

        from api.models import ThreadStatus

        q = select(Thread).where(
            Thread.user_id == user_id,
            Thread.status != ThreadStatus.deleted,
        )
        if status:
            q = q.where(Thread.status == status)
        q = q.order_by(Thread.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_message_count(self, _thread_id: str) -> int:
        """Return the number of HumanMessage entries in the LangGraph checkpoint."""
        return 0  # Filled by history endpoint that replays checkpoint

    async def soft_delete(self, thread_id: str, user_id: str) -> bool:
        """Set status=deleted. Returns False if thread not owned by user."""
        from sqlalchemy import update

        from api.models import ThreadStatus

        result = await self._session.execute(
            update(Thread)
            .where(Thread.id == thread_id, Thread.user_id == user_id)
            .values(status=ThreadStatus.deleted, updated_at=datetime.now(UTC))
            .returning(Thread.id)
        )
        await self._session.commit()
        return result.first() is not None

class PromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str, data: object) -> object:
        import uuid

        from api.models import Prompt
        from api.schemas import PromptCreate

        assert isinstance(data, PromptCreate)
        now = datetime.now(UTC)
        prompt = Prompt(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=data.title,
            content=data.content,
            description=data.description,
            tags=data.tags,
            use_count=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(prompt)
        await self._session.commit()
        await self._session.refresh(prompt)
        return prompt

    async def get(self, prompt_id: str, user_id: str) -> object | None:
        from sqlalchemy import select

        from api.models import Prompt

        result = await self._session.execute(
            select(Prompt).where(Prompt.id == prompt_id, Prompt.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        user_id: str,
        search: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[object]:
        from sqlalchemy import select

        from api.models import Prompt

        q = select(Prompt).where(Prompt.user_id == user_id)
        if search:
            from sqlalchemy import or_

            q = q.where(
                or_(
                    Prompt.title.ilike(f"%{search}%"),
                    Prompt.content.ilike(f"%{search}%"),
                )
            )
        if tags:
            for tag in tags:
                q = q.where(Prompt.tags.contains([tag]))
        q = q.order_by(Prompt.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update(self, prompt_id: str, user_id: str, data: object) -> object | None:
        from sqlalchemy import update

        from api.models import Prompt
        from api.schemas import PromptUpdate

        assert isinstance(data, PromptUpdate)
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if data.title is not None:
            values["title"] = data.title
        if data.content is not None:
            values["content"] = data.content
        if data.description is not None:
            values["description"] = data.description
        if data.tags is not None:
            values["tags"] = data.tags

        await self._session.execute(
            update(Prompt).where(Prompt.id == prompt_id, Prompt.user_id == user_id).values(**values)
        )
        await self._session.commit()
        return await self.get(prompt_id, user_id)

    async def delete(self, prompt_id: str, user_id: str) -> bool:
        from sqlalchemy import delete

        from api.models import Prompt

        result = await self._session.execute(
            delete(Prompt)
            .where(Prompt.id == prompt_id, Prompt.user_id == user_id)
            .returning(Prompt.id)
        )
        await self._session.commit()
        return result.first() is not None

    async def increment_use_count(self, prompt_id: str) -> None:
        from sqlalchemy import update

        from api.models import Prompt

        await self._session.execute(
            update(Prompt).where(Prompt.id == prompt_id).values(use_count=Prompt.use_count + 1)
        )
        await self._session.commit()
