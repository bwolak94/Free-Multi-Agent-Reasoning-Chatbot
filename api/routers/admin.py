from __future__ import annotations

from fastapi import APIRouter

from api.mcp_loader import get_loader

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload")
async def reload_mcp() -> dict[str, str]:
    """Disconnect and reconnect all MCP servers, re-registering their tools."""
    loader = get_loader()
    await loader.reload()
    return {"status": "reloaded"}
