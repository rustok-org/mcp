"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return MCP server health status."""
    return HealthResponse(status="ok")
