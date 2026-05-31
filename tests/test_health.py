"""Health endpoint tests."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    """/health must return 200 and status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["status"] == "ok"
