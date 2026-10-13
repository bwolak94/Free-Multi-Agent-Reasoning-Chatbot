from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from api.auth import get_current_user
from api.database import get_session
from api.repositories import UserThreadRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.models import User

router = APIRouter(prefix="/users", tags=["users"])


class ThreadSummary(BaseModel):
    id: str
    status: str
    title: str | None
    created_at: str
    message_count: int


class MessageResponse(BaseModel):
    role: str
    content: str


@router.get("/me/threads", response_model=list[ThreadSummary])
async def list_my_threads(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadSummary]:
    repo = UserThreadRepository(session)
    threads = await repo.list_by_user(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        status=status,
    )
    return [
        ThreadSummary(
            id=t.id,
            status=t.status.value,
            title=t.title,
            created_at=t.created_at.isoformat(),
            message_count=0,
        )
        for t in threads
    ]


@router.get("/me/threads/{thread_id}/history", response_model=list[MessageResponse])
async def get_thread_history(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MessageResponse]:
    from langchain_core.runnables import RunnableConfig
    from sqlalchemy import select

    from agents.graph import build_graph
    from api.checkpointer import get_checkpointer
    from api.models import Thread as ThreadModel

    result = await session.execute(select(ThreadModel).where(ThreadModel.id == thread_id))
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    config = RunnableConfig(configurable={"thread_id": thread_id})

    messages: list[MessageResponse] = []
    async with get_checkpointer() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        state = await graph.aget_state(config)
        if state and state.values:
            raw_messages: list[Any] = state.values.get("messages", [])
            for msg in raw_messages:
                if isinstance(msg, HumanMessage):
                    role = "user"
                elif isinstance(msg, AIMessage):
                    role = "assistant"
                else:
                    role = "system"
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append(MessageResponse(role=role, content=content))

    return messages
