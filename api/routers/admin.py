from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.config_manager import get_config_manager

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload")
async def reload_config() -> dict[str, Any]:
    """Reload policy rules and MCP servers without restarting the process.

    Returns counts of reloaded rules and MCP servers.
    Raises 422 if any config file contains invalid YAML (running config unchanged).
    """
    result = await get_config_manager().reload()
    if result.has_errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": result.errors},
        )
    return {
        "status": "ok",
        "reloaded_rules": result.reloaded_rules,
        "reloaded_mcp_servers": result.reloaded_mcp_servers,
    }
