"""Scaffold smoke tests."""

from rustok_mcp.main import app


def test_app_instance_exists() -> None:
    """FastAPI app instance must be importable and truthy."""
    assert app is not None
    assert app.title == "Rustok MCP Server"
