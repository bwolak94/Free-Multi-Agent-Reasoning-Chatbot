from __future__ import annotations

import pytest

from tools.base import (
    DuplicateToolError,
    ToolDescriptor,
    ToolNotFoundError,
    ToolRegistry,
    _build_input_model,
    _RegisteredTool,
    get_registry,
    tool,
)


@pytest.fixture(autouse=True)
def isolated_registry() -> ToolRegistry:
    """Give each test a fresh registry to avoid cross-test pollution."""
    registry = ToolRegistry()
    registry.clear()
    yield registry
    registry.clear()


# ---------------------------------------------------------------------------
# ToolDescriptor
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tool_descriptor_defaults() -> None:
    d = ToolDescriptor(name="x.y", description="desc", input_schema={})
    assert d.risk == "low"
    assert d.tags == []


@pytest.mark.unit
def test_tool_descriptor_high_risk() -> None:
    d = ToolDescriptor(name="x.y", description="desc", input_schema={}, risk="high")
    assert d.risk == "high"


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_is_singleton() -> None:
    r1 = ToolRegistry()
    r2 = ToolRegistry()
    assert r1 is r2


@pytest.mark.unit
async def test_register_and_get() -> None:
    async def _fn(query: str) -> str:
        return query

    input_model = _build_input_model(_fn, "test_fn")
    descriptor = ToolDescriptor(name="test.get", description="d", input_schema={})
    registered = _RegisteredTool(fn=_fn, descriptor=descriptor, input_model=input_model)
    get_registry().register(registered)

    fetched = get_registry().get("test.get")
    assert fetched.descriptor.name == "test.get"


@pytest.mark.unit
def test_get_unknown_raises_tool_not_found() -> None:
    with pytest.raises(ToolNotFoundError):
        get_registry().get("no.such.tool")


@pytest.mark.unit
async def test_duplicate_name_raises() -> None:
    async def _fn(x: str) -> str:
        return x

    input_model = _build_input_model(_fn, "dup_fn")
    descriptor = ToolDescriptor(name="dup.tool", description="d", input_schema={})
    t = _RegisteredTool(fn=_fn, descriptor=descriptor, input_model=input_model)
    get_registry().register(t)

    with pytest.raises(DuplicateToolError):
        get_registry().register(t)


@pytest.mark.unit
async def test_list_all_returns_descriptors() -> None:
    async def _fn(q: str) -> str:
        return q

    input_model = _build_input_model(_fn, "list_fn")
    for name in ("a.tool", "b.tool"):
        d = ToolDescriptor(name=name, description="d", input_schema={})
        get_registry().register(_RegisteredTool(fn=_fn, descriptor=d, input_model=input_model))

    descriptors = get_registry().list_all()
    names = {d.name for d in descriptors}
    assert {"a.tool", "b.tool"}.issubset(names)


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_tool_decorator_registers() -> None:
    @tool("dec.search", description="A search tool", risk="low", tags=["search"])
    async def _search(_query: str) -> list:
        return []

    fetched = get_registry().get("dec.search")
    assert fetched.descriptor.description == "A search tool"
    assert fetched.descriptor.risk == "low"
    assert "search" in fetched.descriptor.tags


@pytest.mark.unit
async def test_tool_decorator_input_schema_has_fields() -> None:
    @tool("dec.fetch", description="Fetch tool")
    async def _fetch(url: str, timeout: int = 5) -> dict:  # noqa: ARG001
        return {}

    schema = get_registry().get("dec.fetch").descriptor.input_schema
    assert "url" in str(schema)
    assert "timeout" in str(schema)


@pytest.mark.unit
async def test_tool_callable_validates_and_invokes() -> None:
    results = []

    @tool("dec.callable", description="Callable test")
    async def _callable(value: str) -> str:
        results.append(value)
        return value

    registered = get_registry().get("dec.callable")
    ret = await registered(value="hello")
    assert ret == "hello"
    assert results == ["hello"]


@pytest.mark.unit
async def test_tool_decorator_uses_docstring_as_description() -> None:
    @tool("dec.docstring")
    async def _doc(q: str) -> str:
        """First line of docstring."""
        return q

    desc = get_registry().get("dec.docstring").descriptor.description
    assert "First line" in desc


# ---------------------------------------------------------------------------
# _build_input_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_input_model_required_param() -> None:
    async def _fn(query: str) -> str:
        return query

    model = _build_input_model(_fn, "test")
    fields = model.model_fields
    assert "query" in fields
    assert fields["query"].is_required()


@pytest.mark.unit
def test_build_input_model_optional_param() -> None:
    async def _fn(query: str, limit: int = 5) -> str:  # noqa: ARG001
        return query

    model = _build_input_model(_fn, "test")
    fields = model.model_fields
    assert not fields["limit"].is_required()
