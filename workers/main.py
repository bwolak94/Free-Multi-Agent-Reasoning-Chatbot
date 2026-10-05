from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from api.settings import settings
from workers.jobs import run_dummy_job


async def startup(ctx: dict[str, Any]) -> None:
    ctx["redis"] = await aioredis.from_url(settings.redis_url, decode_responses=True)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["redis"].aclose()


class WorkerSettings:
    functions = [run_dummy_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = settings.worker_job_timeout
    keep_result = 3600
    retry_jobs = True
    max_tries = 3
