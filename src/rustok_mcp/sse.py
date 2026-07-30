"""SSE transport for MCP (JSON-RPC over Server-Sent Events)."""

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rustok_mcp.auth import require_auth
from rustok_mcp.capabilities import Session, extract_rustok_capabilities
from rustok_mcp.protocol import JsonRpcRequest, McpProtocol

# require_auth gates every route on this router (/sse and /message). /health
# lives on a separate prefix-less router and stays public.
router = APIRouter(prefix="/mcp", dependencies=[Depends(require_auth)])

# In-memory session store: session_id -> Session
_sessions: dict[str, Session] = {}

# Memory and idle-time bounds for the SSE session store.
MAX_SESSIONS = 256
SESSION_TTL_SECONDS = 600.0
REAP_INTERVAL_SECONDS = 60.0


class _MessageResponse(BaseModel):
    """Acknowledgement for POST /message."""

    status: str


@router.get("/sse")
async def mcp_sse(request: Request) -> StreamingResponse:
    """Establish an SSE connection and return a message endpoint URI.

    The client must POST JSON-RPC requests to the returned endpoint.
    Responses are streamed back via SSE ``message`` events.
    """
    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(status_code=503, detail="too many sessions")

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
    session.last_seen = time.monotonic()
    protocol: McpProtocol = request.app.state.protocol

    # Intercept initialize to store client capabilities (only on first initialize).
    # Capabilities are the rustok-specific list; the standard MCP capabilities
    # object is ignored (SSE stays gated until a list is granted).
    if body.method == "initialize" and not session.capabilities:
        session.capabilities = extract_rustok_capabilities(body.params)

    context = {"capabilities": session.capabilities}
    response = await protocol.handle(body, context)

    if response is not None:
        assert session.queue is not None  # noqa: S101
        await session.queue.put(response.to_wire())

    return _MessageResponse(status="ok")


def reap_stale_sessions(
    sessions: dict[str, Session],
    now: float,
    ttl: float,
) -> list[str]:
    """Evict sessions idle longer than ttl; signal their generators to stop.

    Returns the evicted session ids. Popping directly frees memory even when the
    generator is already dead; the ``__disconnect__`` message is best-effort to
    stop a live generator, whose ``finally`` then no-ops the pop.
    """
    stale = [sid for sid, s in sessions.items() if now - s.last_seen > ttl]
    for sid in stale:
        s = sessions.pop(sid, None)
        if s is not None and s.queue is not None:
            with contextlib.suppress(asyncio.QueueFull):
                s.queue.put_nowait("__disconnect__")
    return stale


async def session_reaper() -> None:
    """Periodically remove idle SSE sessions."""
    while True:
        await asyncio.sleep(REAP_INTERVAL_SECONDS)
        reap_stale_sessions(_sessions, time.monotonic(), SESSION_TTL_SECONDS)
