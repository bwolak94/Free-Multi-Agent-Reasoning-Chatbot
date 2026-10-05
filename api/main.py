from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from api.mcp_loader import get_loader
from api.routers.admin import router as admin_router
from api.routers.jobs import router as jobs_router
from api.routers.threads import router as threads_router
from api.routers.tools import router as tools_router
from api.schemas import DoneEvent, TokenEvent


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from agents.policy import get_policy_engine
    from tools import discover_tools

    discover_tools()
    get_policy_engine().load()
    await get_loader().load()
    yield


app = FastAPI(
    title="Free Multi-Agent Reasoning Chatbot",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads_router)
app.include_router(tools_router)
app.include_router(admin_router)
app.include_router(jobs_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/threads/{thread_id}/stream-test")
async def stream_test(thread_id: str) -> EventSourceResponse:
    async def event_generator() -> AsyncIterator[dict[str, str]]:
        words = ["Hello", " from", " SSE", " stream", "!"]
        for word in words:
            yield {"data": TokenEvent(delta=word).model_dump_json()}
            await asyncio.sleep(0.05)
        yield {"data": DoneEvent(thread_id=thread_id, run_id="test-run").model_dump_json()}

    return EventSourceResponse(event_generator())
