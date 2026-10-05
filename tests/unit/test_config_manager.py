from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.config_manager import ConfigManager, ReloadResult, get_config_manager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_RULES = """\
prompt_rules:
  - scope: global
    text: "Cite sources."
policy_rules:
  - id: approve-video
    when: { tool: "video.generate" }
    action: require_approval
"""

_VALID_MCP = """\
servers:
  - name: fs
    transport: http
    url: http://localhost:3001/mcp
  - name: github
    transport: http
    url: http://localhost:3002/mcp
"""

_INVALID_YAML = "key: [unclosed"


@pytest.fixture(autouse=True)
def reset_manager() -> None:
    import api.config_manager as mod

    mod._manager = None
    yield
    mod._manager = None


def _make_manager(
    tmp_path: Path,
    rules_content: str = _VALID_RULES,
    mcp_content: str = _VALID_MCP,
) -> tuple[ConfigManager, MagicMock, MagicMock]:
    """Build a ConfigManager with mock engine and loader pointing at tmp files."""
    rules_file = tmp_path / "rules" / "default.yaml"
    rules_file.parent.mkdir(parents=True, exist_ok=True)
    rules_file.write_text(rules_content)

    mcp_file = tmp_path / "mcp.yaml"
    mcp_file.write_text(mcp_content)

    mock_engine = MagicMock()
    mock_engine._rules_path = rules_file
    mock_engine.reload = MagicMock()

    mock_loader = MagicMock()
    mock_loader._config_path = mcp_file
    mock_loader.reload = AsyncMock()

    manager = ConfigManager(engine=mock_engine, loader=mock_loader)
    return manager, mock_engine, mock_loader


# ---------------------------------------------------------------------------
# ReloadResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reload_result_has_errors_false() -> None:
    r = ReloadResult(reloaded_rules=3, reloaded_mcp_servers=1)
    assert not r.has_errors


@pytest.mark.unit
def test_reload_result_has_errors_true() -> None:
    r = ReloadResult(errors=["bad.yaml: parse error"])
    assert r.has_errors


# ---------------------------------------------------------------------------
# ConfigManager.reload — success path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_reload_success_returns_counts(tmp_path: Path) -> None:
    manager, mock_engine, mock_loader = _make_manager(tmp_path)
    result = await manager.reload()

    assert not result.has_errors
    assert result.reloaded_rules == 2  # 1 prompt + 1 policy rule
    assert result.reloaded_mcp_servers == 2
    mock_engine.reload.assert_called_once()
    mock_loader.reload.assert_awaited_once()


@pytest.mark.unit
async def test_reload_calls_engine_then_loader(tmp_path: Path) -> None:
    call_order: list[str] = []
    manager, mock_engine, mock_loader = _make_manager(tmp_path)

    def engine_reload() -> None:
        call_order.append("engine")

    async def loader_reload() -> None:
        call_order.append("loader")

    mock_engine.reload.side_effect = engine_reload
    mock_loader.reload.side_effect = loader_reload

    await manager.reload()
    assert call_order == ["engine", "loader"]


# ---------------------------------------------------------------------------
# ConfigManager.reload — invalid YAML → errors, old config retained
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_invalid_rules_yaml_returns_error(tmp_path: Path) -> None:
    manager, mock_engine, mock_loader = _make_manager(tmp_path, rules_content=_INVALID_YAML)
    result = await manager.reload()

    assert result.has_errors
    assert any("default.yaml" in e for e in result.errors)
    mock_engine.reload.assert_not_called()
    mock_loader.reload.assert_not_awaited()


@pytest.mark.unit
async def test_invalid_mcp_yaml_returns_error(tmp_path: Path) -> None:
    manager, mock_engine, mock_loader = _make_manager(tmp_path, mcp_content=_INVALID_YAML)
    result = await manager.reload()

    assert result.has_errors
    assert any("mcp.yaml" in e for e in result.errors)
    mock_engine.reload.assert_not_called()
    mock_loader.reload.assert_not_awaited()


@pytest.mark.unit
async def test_both_invalid_returns_all_errors(tmp_path: Path) -> None:
    manager, mock_engine, _ = _make_manager(
        tmp_path, rules_content=_INVALID_YAML, mcp_content=_INVALID_YAML
    )
    result = await manager.reload()

    assert len(result.errors) == 2
    mock_engine.reload.assert_not_called()


@pytest.mark.unit
async def test_missing_rules_file_no_error(tmp_path: Path) -> None:
    """Missing rules file is treated as empty, not an error."""
    manager, mock_engine, _mock_loader = _make_manager(tmp_path)
    # Delete the rules file after manager is created
    manager._engine._rules_path.unlink()  # type: ignore[attr-defined]

    result = await manager.reload()
    assert not result.has_errors
    assert result.reloaded_rules == 0
    mock_engine.reload.assert_called_once()


@pytest.mark.unit
async def test_missing_mcp_file_no_error(tmp_path: Path) -> None:
    """Missing MCP config is treated as empty, not an error."""
    manager, _, mock_loader = _make_manager(tmp_path)
    manager._loader._config_path.unlink()  # type: ignore[attr-defined]

    result = await manager.reload()
    assert not result.has_errors
    assert result.reloaded_mcp_servers == 0
    mock_loader.reload.assert_awaited_once()


# ---------------------------------------------------------------------------
# ConfigManager.reload — concurrency
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_reload_lock_prevents_concurrent_calls(tmp_path: Path) -> None:
    """Second reload call waits until the first completes."""
    import asyncio

    call_count = 0
    manager, _mock_engine, _mock_loader = _make_manager(tmp_path)

    original_reload = manager._do_reload

    async def slow_reload() -> ReloadResult:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return await original_reload()

    manager._do_reload = slow_reload  # type: ignore[method-assign]

    results = await asyncio.gather(manager.reload(), manager.reload())
    assert call_count == 2  # both ran, but sequentially
    for r in results:
        assert not r.has_errors


# ---------------------------------------------------------------------------
# get_config_manager singleton
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_config_manager_returns_singleton() -> None:
    m1 = get_config_manager()
    m2 = get_config_manager()
    assert m1 is m2
