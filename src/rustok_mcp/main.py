"""FastAPI application entrypoint."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rustok_mcp.config import get_settings
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.health import router as health_router
from rustok_mcp.sse import _sessions
from rustok_mcp.sse import router as sse_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan events."""
    settings = get_settings()
    if settings.inbound_api_key is None:
        logger.warning(
            "inbound auth disabled — set RUSTOK_MCP_INBOUND_API_KEY to require a "
            "bearer token on the SSE transport (never expose MCP publicly without it)"
        )
    gateway_client = GatewayClient(
        base_url=settings.gateway_url,
        api_key=settings.api_key,
    )
    protocol, registry = create_protocol_and_registry(gateway_client)
    app.state.protocol = protocol
    app.state.registry = registry
    try:
        yield
    finally:
        await gateway_client.close()
        # Shutdown: clear all sessions to prevent memory leaks
        _sessions.clear()


app = FastAPI(
    title="Rustok MCP Server",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(sse_router)


def run() -> None:
    """Run the MCP server with uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
