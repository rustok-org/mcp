"""Health endpoint tests."""

import pytest
from httpx import AsyncClient

from rustok_mcp.config import clear_settings_cache


async def test_health_returns_ok(client: AsyncClient) -> None:
    """/health must return 200 and status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["status"] == "ok"


async def test_health_public_when_inbound_key_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health stays public even with inbound auth enabled (no regression)."""
    monkeypatch.setenv("RUSTOK_MCP_INBOUND_API_KEY", "secret")
    clear_settings_cache()
    response = await client.get("/health")
    assert response.status_code == 200
