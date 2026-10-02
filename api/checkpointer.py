from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from api.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langgraph.checkpoint.base import BaseCheckpointSaver


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[BaseCheckpointSaver]:  # type: ignore[type-arg]
    """Yield a checkpointer appropriate for the current environment.

    - USE_SQLITE=true  → AsyncSqliteSaver (dev, no Postgres required)
    - default          → AsyncPostgresSaver (production)

    Usage::

        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
    """
    if settings.use_sqlite:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string("./dev.db") as checkpointer:
            await checkpointer.setup()
            yield checkpointer
    else:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # Convert asyncpg URL to psycopg-compatible URL expected by the checkpointer
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "sqlite+aiosqlite:///",
            "",  # safety: should not reach here when use_sqlite=False
        )

        async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
            await checkpointer.setup()
            yield checkpointer
