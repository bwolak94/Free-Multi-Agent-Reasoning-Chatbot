from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
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
from api.schemas import DoneEvent, ErrorEvent, InterruptEvent, StepEvent, TokenEvent

router = APIRouter(prefix="/threads", tags=["threads"])


class CreateThreadRequest(BaseModel):
    hitl_config: dict[str, Any] | None = None
    thread_id: str | None = None


class CreateThreadResponse(BaseModel):
    id: str


class RunRequest(BaseModel):
    message: str


class ResumeRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    plan: list[dict[str, Any]] | None = None
    tool_args: dict[str, Any] | None = None
    reason: str | None = None


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


async def _stream_graph(
    graph: Any,
    input_: Any,
    config: RunnableConfig,
    repo: ThreadRepository,
    thread_id: str,
    run_id: str,
) -> AsyncIterator[dict[str, str]]:
    """Shared SSE streaming logic for both /runs and /resume."""
    await repo.update_status(thread_id, ThreadStatus.running)
    interrupted = False
    try:
        async for event in graph.astream_events(input_, config=config, version="v2"):
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

        # Check for pending interrupts after stream ends
        state = await graph.aget_state(config)
        pending_interrupts = [
            intr for task in (state.tasks or []) for intr in (task.interrupts or [])
        ]
        if pending_interrupts:
            interrupted = True
            await repo.update_status(thread_id, ThreadStatus.waiting_hitl)
            for intr in pending_interrupts:
                value: dict[str, Any] = intr.value if hasattr(intr, "value") else {}
                subject = value.get("subject", "plan")
                data = value.get("data", {})
                yield {
                    "data": InterruptEvent(
                        subject=subject,
                        data=data,
                    ).model_dump_json()
                }
        else:
            await repo.update_status(thread_id, ThreadStatus.idle)
            yield {"data": DoneEvent(thread_id=thread_id, run_id=run_id).model_dump_json()}

    except Exception as exc:
        if not interrupted:
            await repo.update_status(thread_id, ThreadStatus.error)
        yield {"data": ErrorEvent(code="run_error", message=str(exc)).model_dump_json()}


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

    # Carry hitl_config from thread into graph initial state
    init_state: dict[str, Any] = {
        "messages": [HumanMessage(content=body.message)],
        "hitl_config": thread.hitl_config,
    }

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            async for item in _stream_graph(graph, init_state, config, repo, thread_id, run_id):
                yield item

    return EventSourceResponse(event_stream())


@router.post("/{thread_id}/resume")
async def resume_thread(
    thread_id: str,
    body: ResumeRequest,
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    repo = ThreadRepository(session)
    thread = await repo.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.status != ThreadStatus.waiting_hitl:
        raise HTTPException(status_code=409, detail="Thread is not waiting for HITL approval")

    run_id = make_run_id()
    config = RunnableConfig(configurable={"thread_id": thread_id})

    payload: dict[str, Any] = {"action": body.action}
    if body.plan is not None:
        payload["plan"] = body.plan
    if body.tool_args is not None:
        payload["tool_args"] = body.tool_args
    if body.reason is not None:
        payload["reason"] = body.reason

    resume_input: Command[Any] = Command(resume=payload)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            async for item in _stream_graph(graph, resume_input, config, repo, thread_id, run_id):
                yield item

    return EventSourceResponse(event_stream())
