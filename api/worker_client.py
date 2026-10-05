from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from api.schemas import ProgressEvent
from api.settings import settings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Return the module-level arq connection pool (lazy-initialised)."""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_job(function: str, **kwargs: Any) -> str:
    """Enqueue an arq job and return its ``job_id``."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(function, **kwargs)
    if job is None:
        raise RuntimeError(f"Failed to enqueue job {function!r} (duplicate or full queue)")
    return job.job_id


async def stream_job_progress(
    job_id: str,
    *,
    redis_client: aioredis.Redis | None = None,  # type: ignore[type-arg]
    poll_interval: float = 0.05,
    idle_timeout: float = 30.0,
) -> AsyncIterator[ProgressEvent]:
    """Subscribe to Redis pub/sub and yield ``ProgressEvent`` objects.

    Parameters
    ----------
    job_id:
        The arq job ID whose channel ``job:{job_id}:progress`` to subscribe to.
    redis_client:
        Optional pre-built Redis client (used in tests). When ``None`` a new
        client is created from ``settings.redis_url`` and closed on exit.
    poll_interval:
        How long to sleep between ``get_message()`` polls (seconds).
    idle_timeout:
        Stop the generator if no message arrives within this many seconds.
    """
    owned = redis_client is None
    client: aioredis.Redis = redis_client or aioredis.from_url(  # type: ignore[type-arg]
        settings.redis_url, decode_responses=True
    )
    channel = f"job:{job_id}:progress"
    try:
        async with client.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            idle = 0.0
            while idle < idle_timeout:
                message: dict[str, Any] | None = await pubsub.get_message(
                    ignore_subscribe_messages=True
                )
                if message is not None and message.get("type") == "message":
                    idle = 0.0
                    event = ProgressEvent.model_validate_json(message["data"])
                    yield event
                    if event.percent >= 100:
                        break
                else:
                    await asyncio.sleep(poll_interval)
                    idle += poll_interval
    finally:
        if owned:
            await client.aclose()  # type: ignore[attr-defined]
