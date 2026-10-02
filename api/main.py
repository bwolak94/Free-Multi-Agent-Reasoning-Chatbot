import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from api.routers.threads import router as threads_router
from api.schemas import DoneEvent, TokenEvent

app = FastAPI(
    title="Free Multi-Agent Reasoning Chatbot",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads_router)


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
