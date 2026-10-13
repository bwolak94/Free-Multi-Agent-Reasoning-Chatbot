#!/usr/bin/env python3
"""CLI helper — create a user account directly in the database.

Usage:
    uv run python scripts/create_user.py <username> <password>

The script reads DATABASE_URL from the environment (or .env file).
"""

from __future__ import annotations

import asyncio
import sys


async def main(username: str, password: str) -> None:
    from api.auth import hash_password, new_user_id
    from api.database import get_session
    from api.repositories import UserRepository

    async for session in get_session():
        repo = UserRepository(session)
        existing = await repo.get_by_username(username)
        if existing is not None:
            print(f"Error: user '{username}' already exists.")
            sys.exit(1)

        user = await repo.create(
            user_id=new_user_id(),
            username=username,
            hashed_password=hash_password(password),
        )
        print(f"Created user '{user.username}' (id={user.id})")


if __name__ == "__main__":
    if len(sys.argv) != 3:  # noqa: PLR2004
        print(f"Usage: {sys.argv[0]} <username> <password>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1], sys.argv[2]))
