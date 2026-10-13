from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _auth_headers(user_id: str = "u1", username: str = "alice") -> dict[str, str]:
    from api.auth import create_access_token

    token = create_access_token(user_id, username)
    return {"Authorization": f"Bearer {token}"}


def _fake_user(uid: str = "u1") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.is_active = True
    return u


def _fake_pref(tool_name: str, enabled: bool = True) -> MagicMock:
    p = MagicMock()
    p.tool_name = tool_name
    p.enabled = enabled
    return p


def _fake_session() -> object:
    async def _gen() -> object:
        yield MagicMock()

    return _gen()


# ---------------------------------------------------------------------------
# GET /tools/preferences
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_tool_preferences_returns_all_tools() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_tool_repo = AsyncMock()
    mock_tool_repo.get_all.return_value = [
        _fake_pref("web.search", True),
        _fake_pref("web.fetch", False),
    ]

    fake_tool_1 = MagicMock()
    fake_tool_1.name = "web.search"
    fake_tool_1.description = "Search the web"
    fake_tool_1.risk = "low"

    fake_tool_2 = MagicMock()
    fake_tool_2.name = "web.fetch"
    fake_tool_2.description = "Fetch a URL"
    fake_tool_2.risk = "low"

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.tools.ToolPrefRepository", return_value=mock_tool_repo),
        patch("api.routers.tools.get_registry") as mock_reg,
    ):
        mock_reg.return_value.list_all.return_value = [fake_tool_1, fake_tool_2]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/tools/preferences", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {d["name"] for d in data}
    assert "web.search" in names
    assert "web.fetch" in names


@pytest.mark.unit
async def test_get_tool_preferences_requires_auth() -> None:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/tools/preferences")

    assert resp.status_code == 401


@pytest.mark.unit
async def test_set_tool_preferences_bulk() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_tool_repo = AsyncMock()
    mock_tool_repo.set_bulk.return_value = None

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.tools.ToolPrefRepository", return_value=mock_tool_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(
                "/tools/preferences",
                json={"preferences": {"web.search": True, "web.fetch": False}},
                headers=_auth_headers(),
            )

    assert resp.status_code == 204
    mock_tool_repo.set_bulk.assert_called_once_with("u1", {"web.search": True, "web.fetch": False})


# ---------------------------------------------------------------------------
# select_tool_node filtering
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_select_tool_node_filters_by_enabled_tools() -> None:
    """Disabled tools should not appear in LLM prompt."""
    from agents.tool.nodes import select_tool_node

    fake_tool_a = MagicMock()
    fake_tool_a.name = "web.search"
    fake_tool_a.description = "Search"
    fake_tool_a.input_schema = {}

    fake_tool_b = MagicMock()
    fake_tool_b.name = "code.exec"
    fake_tool_b.description = "Execute code"
    fake_tool_b.input_schema = {}

    state = {
        "plan": [{"goal": "search for X", "agent": "tool", "status": "pending"}],
        "current_step": 0,
        "observations": [],
        "hitl_config": {"enabled_tools": ["web.search"]},
    }

    with patch("agents.tool.nodes.get_registry") as mock_reg:
        mock_reg.return_value.list_all.return_value = [fake_tool_a, fake_tool_b]

        with patch("agents.tool.nodes.get_llm") as mock_llm:
            mock_structured = AsyncMock()
            mock_structured.ainvoke.return_value = MagicMock(
                name="web.search", args={}, rationale="best tool"
            )
            mock_llm.return_value.with_structured_output.return_value = mock_structured

            await select_tool_node(state)

    # The LLM should only have seen web.search — verify via the messages passed
    call_args = mock_structured.ainvoke.call_args[0][0]
    system_content = call_args[0].content
    assert "web.search" in system_content
    assert "code.exec" not in system_content


@pytest.mark.unit
async def test_select_tool_node_no_filter_shows_all_tools() -> None:
    """When hitl_config has no enabled_tools, all tools are shown."""
    from agents.tool.nodes import select_tool_node

    fake_tool_a = MagicMock()
    fake_tool_a.name = "web.search"
    fake_tool_a.description = "Search"
    fake_tool_a.input_schema = {}

    fake_tool_b = MagicMock()
    fake_tool_b.name = "code.exec"
    fake_tool_b.description = "Execute"
    fake_tool_b.input_schema = {}

    state = {
        "plan": [{"goal": "do something", "agent": "tool", "status": "pending"}],
        "current_step": 0,
        "observations": [],
        "hitl_config": {},
    }

    with patch("agents.tool.nodes.get_registry") as mock_reg:
        mock_reg.return_value.list_all.return_value = [fake_tool_a, fake_tool_b]

        with patch("agents.tool.nodes.get_llm") as mock_llm:
            mock_structured = AsyncMock()
            mock_structured.ainvoke.return_value = MagicMock(
                name="web.search", args={}, rationale="best"
            )
            mock_llm.return_value.with_structured_output.return_value = mock_structured

            await select_tool_node(state)

    call_args = mock_structured.ainvoke.call_args[0][0]
    system_content = call_args[0].content
    assert "web.search" in system_content
    assert "code.exec" in system_content
