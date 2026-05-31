"""SSE transport endpoint for MCP (placeholder)."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/mcp")


class SseResponse(BaseModel):
    """Placeholder SSE status response."""

    status: str
    message: str


@router.get("/sse", response_model=SseResponse)
async def mcp_sse() -> SseResponse:
    """Placeholder for MCP SSE transport.

    Full streaming implementation will be added in PR-3.2.
    """
    return SseResponse(
        status="not_implemented",
        message="SSE transport is a placeholder in PR-3.1",
    )
