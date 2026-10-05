from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from agents.policy import PolicyEngine
    from api.mcp_loader import MCPLoader

logger = logging.getLogger(__name__)


@dataclass
class ReloadResult:
    """Structured result returned by ConfigManager.reload()."""

    reloaded_rules: int = 0
    reloaded_mcp_servers: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class ConfigManager:
    """Coordinates hot-reload of policy rules and MCP config under an asyncio lock.

    Rules: validates YAML before applying — invalid file leaves running config intact.
    MCP:   per-server connection failures are silently skipped (logged); only YAML
           parse errors are counted as hard errors.
    Concurrency: a single asyncio.Lock prevents overlapping reloads.
    """

    def __init__(
        self,
        engine: PolicyEngine | None = None,
        loader: MCPLoader | None = None,
    ) -> None:
        from agents.policy import get_policy_engine
        from api.mcp_loader import get_loader

        self._engine: PolicyEngine = engine or get_policy_engine()
        self._loader: MCPLoader = loader or get_loader()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def reload(self) -> ReloadResult:
        """Validate both config files, then atomically reload if all are valid.

        Returns
        -------
        ReloadResult
            ``has_errors == True``  → YAML was invalid; running config unchanged.
            ``has_errors == False`` → both engine and loader successfully reloaded.
        """
        async with self._lock:
            return await self._do_reload()

    async def _do_reload(self) -> ReloadResult:
        errors: list[str] = []
        rules_count = 0
        mcp_count = 0

        # --- Validate rules file ---
        rules_path = self._engine._rules_path
        if rules_path.exists():
            try:
                raw = yaml.safe_load(rules_path.read_text()) or {}
                rules_count = len(raw.get("prompt_rules", [])) + len(raw.get("policy_rules", []))
            except Exception as exc:
                errors.append(f"{rules_path.name}: {exc}")

        # --- Validate MCP config ---
        mcp_path = self._loader._config_path
        if mcp_path.exists():
            try:
                raw = yaml.safe_load(mcp_path.read_text()) or {}
                mcp_count = len(raw.get("servers", []))
            except Exception as exc:
                errors.append(f"{mcp_path.name}: {exc}")

        # Hard errors → return without touching running config
        if errors:
            logger.warning("Reload aborted due to config errors: %s", errors)
            return ReloadResult(errors=errors)

        # Apply reloads
        self._engine.reload()
        logger.info("Policy rules reloaded (%d rules)", rules_count)

        await self._loader.reload()
        logger.info("MCP config reloaded (%d servers configured)", mcp_count)

        return ReloadResult(reloaded_rules=rules_count, reloaded_mcp_servers=mcp_count)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    global _manager
    if _manager is None:
        _manager = ConfigManager()
    return _manager
