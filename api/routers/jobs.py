from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.worker_client import stream_job_progress

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> EventSourceResponse:
    """Stream progress events for a long-running worker job via SSE."""

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        async for event in stream_job_progress(job_id):
            yield {"data": event.model_dump_json()}

    return EventSourceResponse(event_gen())
