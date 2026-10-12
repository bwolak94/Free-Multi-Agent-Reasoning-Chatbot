from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import aioboto3
from sqlalchemy import select, update

from api.models import Artifact, Thread, ThreadStatus
from api.settings import settings

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
