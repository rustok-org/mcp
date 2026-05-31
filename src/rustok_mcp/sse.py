"""SSE transport for MCP (JSON-RPC over Server-Sent Events)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rustok_mcp.protocol import JsonRpcRequest, McpProtocol

router = APIRouter(prefix="/mcp")

# In-memory session store: session_id -> message queue
_sessions: dict[str, asyncio.Queue[str]] = {}


class _MessageResponse(BaseModel):
    """Acknowledgement for POST /message."""

    status: str


@router.get("/sse")
async def mcp_sse(request: Request) -> StreamingResponse:
    """Establish an SSE connection and return a message endpoint URI.

    The client must POST JSON-RPC requests to the returned endpoint.
    Responses are streamed back via SSE ``message`` events.
    """
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue[str] = asyncio.Queue()
    _sessions[session_id] = queue

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Announce the POST endpoint for this session
            endpoint = f"/mcp/message?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                except TimeoutError:
                    # SSE comment keeps the connection alive
                    yield ": keepalive\n\n"
                    continue

                if message == "__disconnect__":
                    break

                yield f"event: message\ndata: {message}\n\n"
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@router.post("/message")
async def mcp_message(request: Request, body: JsonRpcRequest) -> _MessageResponse:
    """Receive a JSON-RPC request and forward the response via SSE."""
    session_id = request.query_params.get("session_id", "")
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    protocol: McpProtocol = request.app.state.protocol
    response = await protocol.handle(body)

    if response is not None:
        await _sessions[session_id].put(response.model_dump_json())

    return _MessageResponse(status="ok")
