from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.database import get_session
from api.repositories import PromptRepository
from api.schemas import PromptCreate, PromptResponse, PromptUpdate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.models import Prompt, User

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _to_response(p: Prompt) -> PromptResponse:
    return PromptResponse(
        id=p.id,
        user_id=p.user_id,
        title=p.title,
        content=p.content,
        description=p.description,
        tags=p.tags,
        use_count=p.use_count,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    body: PromptCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PromptResponse:
    repo = PromptRepository(session)
    prompt = await repo.create(current_user.id, body)
    return _to_response(prompt)  # type: ignore[arg-type]


@router.get("", response_model=list[PromptResponse])
async def list_prompts(
    search: str | None = None,
    tags: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PromptResponse]:
    repo = PromptRepository(session)
    tag_list = tags.split(",") if tags else None
    prompts = await repo.list(
        current_user.id, search=search, tags=tag_list, limit=limit, offset=offset
    )
    return [_to_response(p) for p in prompts]  # type: ignore[arg-type]


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PromptResponse:
    repo = PromptRepository(session)
    prompt = await repo.get(prompt_id, current_user.id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_response(prompt)  # type: ignore[arg-type]


@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str,
    body: PromptCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PromptResponse:
    repo = PromptRepository(session)
    update_data = PromptUpdate(
        title=body.title,
        content=body.content,
        description=body.description,
        tags=body.tags,
    )
    prompt = await repo.update(prompt_id, current_user.id, update_data)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_response(prompt)  # type: ignore[arg-type]


@router.patch("/{prompt_id}", response_model=PromptResponse)
async def patch_prompt(
    prompt_id: str,
    body: PromptUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PromptResponse:
    repo = PromptRepository(session)
    prompt = await repo.update(prompt_id, current_user.id, body)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_response(prompt)  # type: ignore[arg-type]


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = PromptRepository(session)
    deleted = await repo.delete(prompt_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt not found")
