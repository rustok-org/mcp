"""SSE transport for MCP (JSON-RPC over Server-Sent Events)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rustok_mcp.auth import require_auth
from rustok_mcp.capabilities import Session, parse_capabilities
from rustok_mcp.protocol import JsonRpcRequest, McpProtocol

# require_auth gates every route on this router (/sse and /message). /health
# lives on a separate prefix-less router and stays public.
router = APIRouter(prefix="/mcp", dependencies=[Depends(require_auth)])

# In-memory session store: session_id -> Session
_sessions: dict[str, Session] = {}


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
    session = Session(session_id=session_id, queue=asyncio.Queue())
    _sessions[session_id] = session

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Announce the POST endpoint for this session
            endpoint = f"/mcp/message?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint}\n\n"

            while True:
                assert session.queue is not None  # noqa: S101
                try:
                    message = await asyncio.wait_for(session.queue.get(), timeout=30.0)
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

    session = _sessions[session_id]
    protocol: McpProtocol = request.app.state.protocol

    # Intercept initialize to store client capabilities (only on first initialize).
    # Capabilities are the rustok-specific list; the standard MCP capabilities
    # object is ignored (SSE stays gated until a list is granted).
    if body.method == "initialize" and isinstance(body.params, dict) and not session.capabilities:
        raw_caps = body.params.get("capabilities", [])
        if isinstance(raw_caps, list):
            session.capabilities = parse_capabilities(raw_caps)

    context = {"capabilities": session.capabilities}
    response = await protocol.handle(body, context)

    if response is not None:
        assert session.queue is not None  # noqa: S101
        await session.queue.put(response.model_dump_json())

    return _MessageResponse(status="ok")
