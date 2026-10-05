from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class BaseWorkerJob(ABC):
    """Abstract base class for arq worker jobs with Redis progress reporting."""

    def __init__(self, job_id: str, ctx: dict[str, Any]) -> None:
        self.job_id = job_id
        self._redis: aioredis.Redis = ctx["redis"]  # type: ignore[type-arg]

    @abstractmethod
    async def run(self) -> dict[str, Any]: ...

    async def on_progress(self, percent: int, message: str = "") -> None:
        """Publish a progress update to Redis channel ``job:{job_id}:progress``."""
        channel = f"job:{self.job_id}:progress"
        payload = json.dumps(
            {
                "type": "progress",
                "job_id": self.job_id,
                "percent": percent,
                "message": message,
            }
        )
        await self._redis.publish(channel, payload)


class DummyJob(BaseWorkerJob):
    """Minimal job that emits deterministic progress events — used for testing."""

    async def run(self) -> dict[str, Any]:
        for i, step in enumerate(("Preparing", "Processing", "Finishing"), 1):
            await self.on_progress(i * 25, step)
        await self.on_progress(100, "Done")
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# arq job functions (registered in WorkerSettings.functions)
# ---------------------------------------------------------------------------


async def run_dummy_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    """arq job function — executes DummyJob for testing the worker pipeline."""
    return await DummyJob(job_id=job_id, ctx=ctx).run()
