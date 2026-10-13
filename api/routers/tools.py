from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_current_user
from api.database import get_session
from api.repositories import ToolPrefRepository
from tools.base import ToolDescriptor, get_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.models import User

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolPrefResponse(BaseModel):
    name: str
    description: str
    risk: str
    enabled: bool


class BulkPrefRequest(BaseModel):
    preferences: dict[str, bool]


@router.get("", response_model=list[ToolDescriptor])
async def list_tools() -> list[ToolDescriptor]:
    """Return all registered tools with their metadata and input schema."""
    return get_registry().list_all()


@router.get("/preferences", response_model=list[ToolPrefResponse])
async def get_tool_preferences(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ToolPrefResponse]:
    all_tools = get_registry().list_all()
    tool_names = [t.name for t in all_tools]
    tool_map = {t.name: t for t in all_tools}

    repo = ToolPrefRepository(session)
    prefs = await repo.get_all(current_user.id, tool_names)

    return [
        ToolPrefResponse(
            name=p.tool_name,
            description=tool_map[p.tool_name].description if p.tool_name in tool_map else "",
            risk=tool_map[p.tool_name].risk if p.tool_name in tool_map else "unknown",
            enabled=p.enabled,
        )
        for p in prefs
    ]


@router.put("/preferences", status_code=204)
async def set_tool_preferences(
    body: BulkPrefRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = ToolPrefRepository(session)
    await repo.set_bulk(current_user.id, body.preferences)


@router.patch("/preferences/{tool_name}", response_model=ToolPrefResponse)
async def toggle_tool(
    tool_name: str,
    body: dict[str, Any],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToolPrefResponse:
    enabled: bool = bool(body.get("enabled", True))
    repo = ToolPrefRepository(session)
    pref = await repo.set(current_user.id, tool_name, enabled)

    tool_map = {t.name: t for t in get_registry().list_all()}
    tool = tool_map.get(tool_name)

    return ToolPrefResponse(
        name=pref.tool_name,  # type: ignore[attr-defined]
        description=tool.description if tool else "",
        risk=tool.risk if tool else "unknown",
        enabled=pref.enabled,  # type: ignore[attr-defined]
    )
