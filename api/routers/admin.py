from __future__ import annotations

from fastapi import APIRouter

from agents.policy import get_policy_engine
from api.mcp_loader import get_loader

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload")
async def reload_mcp() -> dict[str, str]:
    """Reload MCP tools and policy rules without restarting the server."""
    await get_loader().reload()
    get_policy_engine().reload()
    return {"status": "reloaded"}
