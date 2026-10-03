from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_mcp_adapters.client import MultiServerMCPClient

from tools.base import (
    DuplicateToolError,
    ToolDescriptor,
    ToolRegistry,
    _RegisteredTool,
    get_registry,
)

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp.yaml"


class MCPServerConfig:
    """Parsed configuration for a single MCP server."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.name: str = raw["name"]
        self.transport: str = raw.get("transport", "stdio")
        self.command: list[str] = raw.get("command", [])
        self.url: str = raw.get("url", "")
        self.env: dict[str, str] = raw.get("env", {})

    def to_connection_dict(self) -> dict[str, Any]:
        """Build the connection dict expected by MultiServerMCPClient."""
        if self.transport == "http":
            return {"transport": "streamable_http", "url": self.url}
        # stdio
        if not self.command:
            raise ValueError(f"MCP server {self.name!r} has transport=stdio but no command")
        conn: dict[str, Any] = {"transport": "stdio", "command": self.command[0]}
        if len(self.command) > 1:
            conn["args"] = self.command[1:]
        if self.env:
            conn["env"] = self.env
        return conn


class MCPLoader:
    """Loads MCP servers from config/mcp.yaml and registers their tools."""

    def __init__(
        self,
        config_path: Path = _CONFIG_PATH,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._config_path = config_path
        self._registry = registry or get_registry()
        self._registered_names: list[str] = []

    def _load_config(self) -> list[MCPServerConfig]:
        try:
            raw = yaml.safe_load(self._config_path.read_text())
            return [MCPServerConfig(s) for s in (raw or {}).get("servers", [])]
        except Exception as exc:
            logger.warning("Failed to read MCP config %s: %s", self._config_path, exc)
            return []

    async def load(self) -> None:
        """Connect to all configured MCP servers and register their tools."""
        servers = self._load_config()
        if not servers:
            logger.debug("No MCP servers configured.")
            return

        for server in servers:
            await self._load_server(server)

    async def _load_server(self, server: MCPServerConfig) -> None:
        try:
            conn_dict = server.to_connection_dict()
        except ValueError as exc:
            logger.warning("Skipping MCP server %r: %s", server.name, exc)
            return

        connections = {server.name: conn_dict}
        try:
            client = MultiServerMCPClient(connections)  # type: ignore[arg-type]
            lc_tools = await client.get_tools(server_name=server.name)
        except Exception as exc:
            logger.warning("MCP server %r unavailable — skipping. Error: %s", server.name, exc)
            return

        registered = 0
        for lc_tool in lc_tools:
            tool_name = f"mcp.{server.name}.{lc_tool.name}"
            descriptor = ToolDescriptor(
                name=tool_name,
                description=lc_tool.description or "",
                input_schema=lc_tool.args_schema.model_json_schema()  # type: ignore[union-attr]
                if hasattr(lc_tool, "args_schema") and lc_tool.args_schema
                else {},
                risk="low",
                tags=["mcp", server.name],
            )

            def _make_invoke(t: Any) -> Any:
                async def _inner(**kwargs: Any) -> Any:
                    return await t.ainvoke(kwargs)

                return _inner

            _invoke = _make_invoke(lc_tool)

            registered_tool = _RegisteredTool(
                fn=_invoke, descriptor=descriptor, input_model=_make_passthrough_model(descriptor)
            )
            try:
                self._registry.register(registered_tool)
                self._registered_names.append(tool_name)
                registered += 1
            except DuplicateToolError:
                logger.warning("MCP tool %r already registered — skipping.", tool_name)

        logger.info(
            "MCP server %r: registered %d tool(s): %s",
            server.name,
            registered,
            [f"mcp.{server.name}.{t.name}" for t in lc_tools],
        )

    async def reload(self) -> None:
        """Unregister current MCP tools and re-load from config."""
        # Remove previously registered MCP tools from registry
        for name in self._registered_names:
            self._registry._tools.pop(name, None)
        self._registered_names.clear()
        await self.load()


def _make_passthrough_model(descriptor: ToolDescriptor) -> Any:
    """Build a minimal Pydantic model that accepts any kwargs for MCP tools."""
    from pydantic import BaseModel

    class PassthroughModel(BaseModel):
        model_config = {"extra": "allow"}

    PassthroughModel.__name__ = f"{descriptor.name}_input"
    return PassthroughModel


_loader: MCPLoader | None = None


def get_loader() -> MCPLoader:
    global _loader
    if _loader is None:
        _loader = MCPLoader()
    return _loader
