"""FastAPI application entrypoint."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rustok_mcp.config import get_settings
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.health import router as health_router
from rustok_mcp.sse import _sessions, session_reaper
from rustok_mcp.sse import router as sse_router
from rustok_mcp.telemetry import init_telemetry

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
    reaper = asyncio.create_task(session_reaper())
    try:
        yield
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper
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
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    settings = get_settings()
    # JSON logging always; OTLP tracing only when RUSTOK_OTLP_ENDPOINT is set.
    if init_telemetry(settings.app_name, settings.log_level):
        # /health is excluded — the Docker healthcheck would otherwise emit a
        # span every 30s.
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    # log_config=None: defer to the JSON root logging configured in init_telemetry
    # (otherwise uvicorn installs its own text formatter).
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )
