from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.mcp_loader import MCPLoader, MCPServerConfig
from tools.base import ToolRegistry, get_registry


@pytest.fixture(autouse=True)
def isolated_registry() -> ToolRegistry:
    registry = get_registry()
    registry.clear()
    yield registry
    registry.clear()


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text("servers: []\n")
    return cfg


# ---------------------------------------------------------------------------
# MCPServerConfig
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_server_config_stdio() -> None:
    cfg = MCPServerConfig(
        {"name": "fs", "transport": "stdio", "command": ["docker", "run", "mcp/fs"]}
    )
    conn = cfg.to_connection_dict()
    assert conn["transport"] == "stdio"
    assert conn["command"] == "docker"
    assert conn["args"] == ["run", "mcp/fs"]


@pytest.mark.unit
def test_server_config_http() -> None:
    cfg = MCPServerConfig({"name": "gh", "transport": "http", "url": "http://localhost:3001/mcp"})
    conn = cfg.to_connection_dict()
    assert conn["transport"] == "streamable_http"
    assert conn["url"] == "http://localhost:3001/mcp"


@pytest.mark.unit
def test_server_config_stdio_missing_command_raises() -> None:
    cfg = MCPServerConfig({"name": "bad", "transport": "stdio"})
    with pytest.raises(ValueError, match="no command"):
        cfg.to_connection_dict()


# ---------------------------------------------------------------------------
# MCPLoader
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_load_empty_config(tmp_config: Path) -> None:
    loader = MCPLoader(config_path=tmp_config)
    await loader.load()
    assert get_registry().list_all() == []


@pytest.mark.unit
async def test_load_missing_config_logs_warning(tmp_path: Path) -> None:
    loader = MCPLoader(config_path=tmp_path / "nonexistent.yaml")
    await loader.load()  # Should not raise
    assert get_registry().list_all() == []


@pytest.mark.unit
async def test_load_registers_mcp_tools(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: filesystem\n    transport: http\n    url: http://localhost:3001/mcp\n"
    )

    mock_tool_a = MagicMock()
    mock_tool_a.name = "read_file"
    mock_tool_a.description = "Read a file"
    mock_tool_a.args_schema = None

    mock_tool_b = MagicMock()
    mock_tool_b.name = "write_file"
    mock_tool_b.description = "Write a file"
    mock_tool_b.args_schema = None

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[mock_tool_a, mock_tool_b])

    with patch("api.mcp_loader.MultiServerMCPClient", return_value=mock_client):
        loader = MCPLoader(config_path=cfg)
        await loader.load()

    names = {d.name for d in get_registry().list_all()}
    assert "mcp.filesystem.read_file" in names
    assert "mcp.filesystem.write_file" in names


@pytest.mark.unit
async def test_load_unavailable_server_skips(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: offline\n    transport: http\n    url: http://localhost:9999/mcp\n"
    )

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("api.mcp_loader.MultiServerMCPClient", return_value=mock_client):
        loader = MCPLoader(config_path=cfg)
        await loader.load()  # Should not raise

    assert get_registry().list_all() == []


@pytest.mark.unit
async def test_mcp_tool_namespaced_correctly(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: github\n    transport: http\n    url: http://localhost:3002/mcp\n"
    )

    mock_tool = MagicMock()
    mock_tool.name = "create_issue"
    mock_tool.description = "Create an issue"
    mock_tool.args_schema = None

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[mock_tool])

    with patch("api.mcp_loader.MultiServerMCPClient", return_value=mock_client):
        loader = MCPLoader(config_path=cfg)
        await loader.load()

    descriptor = get_registry().get("mcp.github.create_issue").descriptor
    assert descriptor.name == "mcp.github.create_issue"
    assert "mcp" in descriptor.tags
    assert "github" in descriptor.tags


@pytest.mark.unit
async def test_reload_clears_and_re_registers(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: fs\n    transport: http\n    url: http://localhost:3001/mcp\n"
    )

    mock_tool = MagicMock()
    mock_tool.name = "list_dir"
    mock_tool.description = "List directory"
    mock_tool.args_schema = None

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[mock_tool])

    with patch("api.mcp_loader.MultiServerMCPClient", return_value=mock_client):
        loader = MCPLoader(config_path=cfg)
        await loader.load()
        assert "mcp.fs.list_dir" in {d.name for d in get_registry().list_all()}

        await loader.reload()
        assert "mcp.fs.list_dir" in {d.name for d in get_registry().list_all()}


@pytest.mark.unit
async def test_duplicate_tool_skipped_on_reload(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: fs\n    transport: http\n    url: http://localhost:3001/mcp\n"
    )

    mock_tool = MagicMock()
    mock_tool.name = "read"
    mock_tool.description = "Read"
    mock_tool.args_schema = None

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[mock_tool])

    with patch("api.mcp_loader.MultiServerMCPClient", return_value=mock_client):
        loader = MCPLoader(config_path=cfg)
        await loader.load()
        # Second load without reload → duplicate, should be skipped silently
        await loader._load_server(
            MCPServerConfig({"name": "fs", "transport": "http", "url": "http://x/mcp"})
        )

    # Only one registration
    names = [d.name for d in get_registry().list_all() if d.name.startswith("mcp.fs")]
    assert names.count("mcp.fs.read") == 1


@pytest.mark.unit
async def test_admin_reload_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from api.config_manager import ReloadResult
    from api.database import get_session
    from api.main import app
    from api.models import Base
    from api.settings import settings

    settings.use_sqlite = True
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session() -> AsyncSession:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session

    mock_result = ReloadResult(reloaded_rules=3, reloaded_mcp_servers=1)
    with patch("api.config_manager.ConfigManager.reload", AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/admin/reload")

    app.dependency_overrides.clear()
    await engine.dispose()
    settings.use_sqlite = False

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["reloaded_rules"] == 3
    assert body["reloaded_mcp_servers"] == 1
