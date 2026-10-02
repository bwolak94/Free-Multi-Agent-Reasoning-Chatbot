from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import build_graph, make_run_id
from api.checkpointer import get_checkpointer
from api.database import get_session
from api.models import ThreadStatus
from api.repositories import ThreadRepository
from api.schemas import DoneEvent, ErrorEvent, StepEvent, TokenEvent

router = APIRouter(prefix="/threads", tags=["threads"])


class CreateThreadRequest(BaseModel):
    hitl_config: dict[str, Any] | None = None
    thread_id: str | None = None


class CreateThreadResponse(BaseModel):
    id: str


class RunRequest(BaseModel):
    message: str


class ThreadResponse(BaseModel):
    id: str
    status: str
    hitl_config: dict[str, Any] | None


@router.post("", response_model=CreateThreadResponse, status_code=201)
async def create_thread(
    body: CreateThreadRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateThreadResponse:
    repo = ThreadRepository(session)
    thread = await repo.create(
        hitl_config=body.hitl_config,
        thread_id=body.thread_id or str(uuid.uuid4()),
    )
    return CreateThreadResponse(id=thread.id)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_session),
) -> ThreadResponse:
    repo = ThreadRepository(session)
    thread = await repo.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadResponse(
        id=thread.id,
        status=thread.status.value,
        hitl_config=thread.hitl_config,
    )


@router.post("/{thread_id}/runs")
async def run_thread(
    thread_id: str,
    body: RunRequest,
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    repo = ThreadRepository(session)
    thread = await repo.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    run_id = make_run_id()
    config = RunnableConfig(configurable={"thread_id": thread_id})

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        await repo.update_status(thread_id, ThreadStatus.running)
        try:
            async with get_checkpointer() as checkpointer:
                graph = build_graph(checkpointer=checkpointer)
                async for event in graph.astream_events(
                    {"messages": [HumanMessage(content=body.message)]},
                    config=config,
                    version="v2",
                ):
                    kind = event.get("event", "")
                    name = event.get("name", "")

                    if kind == "on_chain_start" and name not in ("LangGraph", ""):
                        yield {"data": StepEvent(node=name, status="started").model_dump_json()}

                    elif kind == "on_chain_end" and name not in ("LangGraph", ""):
                        yield {"data": StepEvent(node=name, status="done").model_dump_json()}

                    elif kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            yield {"data": TokenEvent(delta=chunk.content).model_dump_json()}

            await repo.update_status(thread_id, ThreadStatus.idle)
            yield {"data": DoneEvent(thread_id=thread_id, run_id=run_id).model_dump_json()}

        except Exception as exc:
            await repo.update_status(thread_id, ThreadStatus.error)
            yield {"data": ErrorEvent(code="run_error", message=str(exc)).model_dump_json()}

    return EventSourceResponse(event_stream())
