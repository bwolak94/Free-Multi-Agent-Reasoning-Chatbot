from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_thread(
    thread_id: str = "t1",
    user_id: str = "u1",
    status: str = "idle",
    title: str | None = "Hello",
) -> MagicMock:
    t = MagicMock()
    t.id = thread_id
    t.user_id = user_id
    t.status = MagicMock()
    t.status.value = status
    t.title = title
    t.created_at = MagicMock()
    t.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
    return t


# ---------------------------------------------------------------------------
# UserThreadRepository
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_list_by_user_returns_owned_threads() -> None:
    from api.auth import create_access_token
    from api.main import app

    token = create_access_token("u1", "alice")

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.is_active = True

    thread = _make_thread()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_thread_repo = AsyncMock()
    mock_thread_repo.list_by_user.return_value = [thread]

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.users.UserThreadRepository", return_value=mock_thread_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/users/me/threads",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "t1"


@pytest.mark.unit
async def test_list_my_threads_requires_auth() -> None:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/users/me/threads")

    assert resp.status_code == 401


@pytest.mark.unit
async def test_delete_thread_returns_204() -> None:
    from api.auth import create_access_token
    from api.main import app

    token = create_access_token("u1", "alice")

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.is_active = True

    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_thread_repo = AsyncMock()
    mock_thread_repo.soft_delete.return_value = True

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.threads.UserThreadRepository", return_value=mock_thread_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(
                "/threads/t1",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 204


@pytest.mark.unit
async def test_delete_foreign_thread_returns_404() -> None:
    from api.auth import create_access_token
    from api.main import app

    token = create_access_token("u1", "alice")

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.is_active = True

    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_thread_repo = AsyncMock()
    mock_thread_repo.soft_delete.return_value = False

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.threads.UserThreadRepository", return_value=mock_thread_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(
                "/threads/foreign",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 404


@pytest.mark.unit
async def test_list_threads_pagination_params() -> None:
    from api.auth import create_access_token
    from api.main import app

    token = create_access_token("u1", "alice")

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.is_active = True

    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = fake_user

    mock_thread_repo = AsyncMock()
    mock_thread_repo.list_by_user.return_value = []

    with (
        patch("api.repositories.UserRepository", return_value=mock_user_repo),
        patch("api.database.get_session", return_value=_fake_session()),
        patch("api.routers.users.UserThreadRepository", return_value=mock_thread_repo),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/users/me/threads?limit=5&offset=10",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    mock_thread_repo.list_by_user.assert_called_once_with(
        user_id="u1", limit=5, offset=10, status=None
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_session() -> object:
    async def _gen() -> object:
        yield MagicMock()

    return _gen()
