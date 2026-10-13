from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_prompt(pid: str = "p1", user_id: str = "u1") -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.user_id = user_id
    p.title = "My Prompt"
    p.content = "Do something with {{topic}}"
    p.description = None
    p.tags = ["research"]
    p.use_count = 0
    p.created_at = MagicMock()
    p.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
    p.updated_at = MagicMock()
    p.updated_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
    return p


def _auth_headers(user_id: str = "u1", username: str = "alice") -> dict[str, str]:
    from api.auth import create_access_token

    token = create_access_token(user_id, username)
    return {"Authorization": f"Bearer {token}"}


def _fake_user(uid: str = "u1") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.is_active = True
    return u


@pytest.mark.unit
async def test_create_prompt_returns_201() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_prompt_repo = AsyncMock()
    mock_prompt_repo.create.return_value = _make_prompt()

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.prompts.PromptRepository", return_value=mock_prompt_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/prompts",
                json={"title": "My Prompt", "content": "Do something", "tags": ["research"]},
                headers=_auth_headers(),
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "p1"
    assert data["title"] == "My Prompt"


@pytest.mark.unit
async def test_list_prompts_returns_200() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_prompt_repo = AsyncMock()
    mock_prompt_repo.list.return_value = [_make_prompt(), _make_prompt("p2")]

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.prompts.PromptRepository", return_value=mock_prompt_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/prompts", headers=_auth_headers())

    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.unit
async def test_delete_prompt_returns_204() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_prompt_repo = AsyncMock()
    mock_prompt_repo.delete.return_value = True

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.prompts.PromptRepository", return_value=mock_prompt_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete("/prompts/p1", headers=_auth_headers())

    assert resp.status_code == 204


@pytest.mark.unit
async def test_delete_foreign_prompt_returns_404() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_prompt_repo = AsyncMock()
    mock_prompt_repo.delete.return_value = False

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.prompts.PromptRepository", return_value=mock_prompt_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete("/prompts/foreign", headers=_auth_headers())

    assert resp.status_code == 404


@pytest.mark.unit
async def test_get_prompt_not_found_returns_404() -> None:
    from api.main import app

    fake_user = _fake_user()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_prompt_repo = AsyncMock()
    mock_prompt_repo.get.return_value = None

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.prompts.PromptRepository", return_value=mock_prompt_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/prompts/missing", headers=_auth_headers())

    assert resp.status_code == 404


@pytest.mark.unit
async def test_prompts_requires_auth() -> None:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/prompts")

    assert resp.status_code == 401


def _fake_session() -> object:
    async def _gen() -> object:
        yield MagicMock()

    return _gen()
