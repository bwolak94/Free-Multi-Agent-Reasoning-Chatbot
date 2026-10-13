from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hash_and_verify_password() -> None:
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)


@pytest.mark.unit
def test_verify_wrong_password() -> None:
    hashed = hash_password("correct")
    assert not verify_password("wrong", hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_and_decode_token() -> None:
    token = create_access_token("user-1", "alice")
    payload = decode_token(token)
    assert payload.sub == "user-1"
    assert payload.username == "alice"
    assert payload.exp > datetime.now(UTC)


@pytest.mark.unit
def test_decode_invalid_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.token")
    assert exc_info.value.status_code == 401


@pytest.mark.unit
def test_decode_expired_token_raises_401() -> None:
    from jose import jwt

    from api.settings import settings

    expired_payload = {
        "sub": "user-1",
        "username": "alice",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, settings.secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(expired_token)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_current_user_no_credentials_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=None)
    assert exc_info.value.status_code == 401


@pytest.mark.unit
async def test_get_current_user_valid_token_returns_user() -> None:
    token = create_access_token("user-42", "bob")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = MagicMock()
    fake_user.id = "user-42"
    fake_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = fake_user

    with patch("api.repositories.UserRepository", return_value=mock_repo):

        async def fake_get_session():  # type: ignore[no-untyped-def]
            yield MagicMock()

        with patch("api.database.get_session", fake_get_session):
            user = await get_current_user(credentials=credentials)

    assert user.id == "user-42"


@pytest.mark.unit
async def test_get_current_user_inactive_raises_401() -> None:
    token = create_access_token("user-99", "carol")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = MagicMock()
    fake_user.id = "user-99"
    fake_user.is_active = False

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = fake_user

    with patch("api.repositories.UserRepository", return_value=mock_repo):

        async def fake_get_session():  # type: ignore[no-untyped-def]
            yield MagicMock()

        with (
            patch("api.database.get_session", fake_get_session),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_login_endpoint_valid_credentials() -> None:
    from httpx import ASGITransport, AsyncClient

    from api.auth import hash_password
    from api.main import app

    fake_user = MagicMock()
    fake_user.id = "user-1"
    fake_user.username = "alice"
    fake_user.hashed_password = hash_password("password123")
    fake_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_username.return_value = fake_user

    with patch("api.routers.auth.UserRepository", return_value=mock_repo):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/auth/login", json={"username": "alice", "password": "password123"}
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.unit
async def test_login_endpoint_wrong_password_returns_401() -> None:
    from httpx import ASGITransport, AsyncClient

    from api.auth import hash_password
    from api.main import app

    fake_user = MagicMock()
    fake_user.id = "user-1"
    fake_user.username = "alice"
    fake_user.hashed_password = hash_password("correct")
    fake_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_username.return_value = fake_user

    with patch("api.routers.auth.UserRepository", return_value=mock_repo):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/login", json={"username": "alice", "password": "wrong"})

    assert resp.status_code == 401


@pytest.mark.unit
async def test_login_endpoint_unknown_user_returns_401() -> None:
    from httpx import ASGITransport, AsyncClient

    from api.main import app

    mock_repo = AsyncMock()
    mock_repo.get_by_username.return_value = None

    with patch("api.routers.auth.UserRepository", return_value=mock_repo):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/login", json={"username": "nobody", "password": "pass"})

    assert resp.status_code == 401
