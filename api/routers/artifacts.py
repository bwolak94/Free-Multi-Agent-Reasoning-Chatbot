from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.database import get_session
from api.repositories import ArtifactRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class ArtifactResponse(BaseModel):
    artifact_id: str
    url: str
    artifact_type: str
    created_at: datetime
    expires_at: datetime


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
) -> ArtifactResponse:
    """Return artifact metadata and a time-limited presigned URL."""
    repo = ArtifactRepository(session)

    artifact = await repo.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if artifact.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Artifact has expired")

    url = await repo.presigned_url(artifact_id)
    if url is None:
        raise HTTPException(status_code=500, detail="Could not generate presigned URL")

    return ArtifactResponse(
        artifact_id=artifact.id,
        url=url,
        artifact_type=artifact.artifact_type,
        created_at=artifact.created_at,
        expires_at=artifact.expires_at,
    )
