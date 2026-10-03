from __future__ import annotations

import functools
import inspect
import logging
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, create_model

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

RiskLevel = Literal["low", "high"]


class ToolDescriptor(BaseModel):
    """Metadata for a registered tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk: RiskLevel = "low"
    tags: list[str] = []


class ToolNotFoundError(KeyError):
    """Raised when a tool name is not found in the registry."""


class DuplicateToolError(ValueError):
    """Raised when registering a tool name that already exists."""


class ToolRegistry:
    """Singleton registry of all available tools."""

    _instance: ToolRegistry | None = None
    _tools: dict[str, _RegisteredTool]

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: _RegisteredTool) -> None:
        if tool.descriptor.name in self._tools:
            raise DuplicateToolError(
                f"Tool {tool.descriptor.name!r} is already registered. Names must be unique."
            )
        self._tools[tool.descriptor.name] = tool
        logger.debug("Registered tool %r (risk=%s)", tool.descriptor.name, tool.descriptor.risk)

    def get(self, name: str) -> _RegisteredTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(
                f"Tool {name!r} not found. Available: {list(self._tools)}"
            ) from None

    def list_all(self) -> list[ToolDescriptor]:
        return [t.descriptor for t in self._tools.values()]

    def clear(self) -> None:
        """Reset registry — used in tests only."""
        self._tools.clear()


class _RegisteredTool:
    """Wraps an async callable with its descriptor."""

    def __init__(
        self,
        fn: Callable[..., Any],
        descriptor: ToolDescriptor,
        input_model: type[BaseModel],
    ) -> None:
        self._fn = fn
        self.descriptor = descriptor
        self.input_model = input_model
        functools.update_wrapper(self, fn)

    async def __call__(self, **kwargs: Any) -> Any:
        validated = self.input_model(**kwargs)
        return await self._fn(**validated.model_dump())

    def __repr__(self) -> str:
        return f"<Tool {self.descriptor.name!r}>"


def _build_input_model(fn: Callable[..., Any], name: str) -> type[BaseModel]:
    """Create a Pydantic model from the function's type-annotated parameters."""
    sig = inspect.signature(fn)
    fields: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else Any
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (annotation, default)
    return create_model(f"{name}_input", **fields)


_registry = ToolRegistry()


def tool(
    name: str,
    *,
    description: str = "",
    risk: RiskLevel = "low",
    timeout: int = 30,
    tags: list[str] | None = None,
) -> Callable[[Callable[..., Any]], _RegisteredTool]:
    """Decorator that registers an async function as a tool.

    Usage::

        @tool("web.search", description="Search the web", risk="low", tags=["search"])
        async def web_search_tool(query: str, max_results: int = 5) -> list[dict]:
            ...
    """

    def decorator(fn: Callable[..., Any]) -> _RegisteredTool:
        desc = description or (fn.__doc__ or "").strip().split("\n")[0]
        input_model = _build_input_model(fn, name.replace(".", "_"))
        descriptor = ToolDescriptor(
            name=name,
            description=desc,
            input_schema=input_model.model_json_schema(),
            risk=risk,
            tags=tags or [],
        )
        registered = _RegisteredTool(fn=fn, descriptor=descriptor, input_model=input_model)
        registered._timeout = timeout  # type: ignore[attr-defined]
        _registry.register(registered)
        return registered

    return decorator


def get_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    return _registry
