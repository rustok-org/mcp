"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from rustok_mcp.config import clear_settings_cache
from rustok_mcp.main import app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the settings cache before every test.

    Ensures that monkeypatched env vars are picked up by get_settings().
    """
    clear_settings_cache()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Yield an HTTP test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
