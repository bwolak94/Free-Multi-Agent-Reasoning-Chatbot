from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger(__name__)

_DISCOVERED = False


def discover_tools() -> None:
    """Import all modules in the ``tools/`` package so @tool decorators register.

    Called once at application startup. Safe to call multiple times.
    """
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True

    pkg_path = str(Path(__file__).parent)
    for module_info in pkgutil.iter_modules([pkg_path]):
        if module_info.name.startswith("_"):
            continue
        module_name = f"tools.{module_info.name}"
        try:
            importlib.import_module(module_name)
            logger.debug("Discovered tools module: %s", module_name)
        except Exception as exc:
            logger.warning("Failed to import tools module %s: %s", module_name, exc)
