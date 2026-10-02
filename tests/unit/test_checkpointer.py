from __future__ import annotations

import pytest

from api.checkpointer import get_checkpointer
from api.settings import settings


@pytest.mark.unit
async def test_sqlite_checkpointer_yields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_sqlite", True)
    async with get_checkpointer() as cp:
        assert cp is not None


@pytest.mark.unit
async def test_sqlite_checkpointer_setup_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup() creates the checkpoint tables — should not raise."""
    monkeypatch.setattr(settings, "use_sqlite", True)
    async with get_checkpointer() as cp:
        # If setup() failed, get_checkpointer would have raised
        assert cp is not None
