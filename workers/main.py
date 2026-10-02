from arq import cron
from arq.connections import RedisSettings


async def startup(ctx: dict) -> None:  # type: ignore[type-arg]
    pass


async def shutdown(ctx: dict) -> None:  # type: ignore[type-arg]
    pass


class WorkerSettings:
    functions: list[object] = []
    cron_jobs: list[object] = [cron]
    redis_settings = RedisSettings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 600  # 10 minutes
