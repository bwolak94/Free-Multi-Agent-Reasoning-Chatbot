from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from api.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.models import User

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


class TokenPayload(BaseModel):
    sub: str  # user_id
    username: str
    exp: datetime


def create_access_token(user_id: str, username: str) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.access_token_expire_hours)
    data: dict[str, Any] = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(data, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return TokenPayload(**payload)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession | None = None,
) -> User:
    """Require a valid Bearer token. Raises 401 if missing or invalid."""
    from api.database import get_session
    from api.repositories import UserRepository

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    # Use injected session or open a new one
    async def _fetch(db: AsyncSession) -> User:
        repo = UserRepository(db)
        user = await repo.get_by_id(payload.sub)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user

    if session is not None:
        return await _fetch(session)

    async for db in get_session():
        return await _fetch(db)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    """Return current user if a valid token is present, else None (no error)."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def new_user_id() -> str:
    return str(uuid.uuid4())
