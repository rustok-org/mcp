"""FastAPI application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rustok_mcp.config import get_settings
from rustok_mcp.health import router as health_router
from rustok_mcp.sse import router as sse_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan events."""
    get_settings()  # validate settings load correctly
    yield


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
        "rustok_mcp.main:app",
        host="127.0.0.1",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
