from __future__ import annotations

from fastapi import APIRouter

from tools.base import ToolDescriptor, get_registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolDescriptor])
async def list_tools() -> list[ToolDescriptor]:
    """Return all registered tools with their metadata and input schema."""
    return get_registry().list_all()
