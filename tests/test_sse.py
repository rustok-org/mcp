"""SSE transport tests."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from rustok_mcp.capabilities import Session
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcRequest
from rustok_mcp.sse import _sessions, mcp_message, mcp_sse


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    """Remove test sessions between tests."""
    _sessions.clear()


async def test_sse_yields_endpoint_event() -> None:
    """The SSE stream starts with an endpoint event containing the session URI."""
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {}

    response = await mcp_sse(mock_request)
    assert response.media_type == "text/event-stream"

    body = ""
    async for chunk in response.body_iterator:
        body += chunk
        if "\n\n" in body:
            break

    assert "event: endpoint" in body
    assert "/mcp/message?session_id=" in body


async def test_sse_message_roundtrip() -> None:
    """POST /mcp/message forwards the JSON-RPC response via SSE queue."""
    session_id = "test-session"
    queue: asyncio.Queue[str] = asyncio.Queue()
    _sessions[session_id] = Session(session_id=session_id, queue=queue)

    protocol, _registry = create_protocol_and_registry()

    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {"session_id": session_id}
    mock_request.app.state.protocol = protocol

    init_request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
    )
    post_response = await mcp_message(mock_request, init_request)
    assert post_response.status == "ok"

    message = await asyncio.wait_for(queue.get(), timeout=1.0)
    data = json.loads(message)
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"


async def test_sse_message_missing_session_id() -> None:
    """POST /mcp/message without session_id returns 404."""
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {}

    init_request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
    )
    with pytest.raises(HTTPException) as exc_info:
        await mcp_message(mock_request, init_request)
    assert exc_info.value.status_code == 404


async def test_sse_message_invalid_session_id() -> None:
    """POST /mcp/message with unknown session_id returns 404."""
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {"session_id": "unknown"}

    init_request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
    )
    with pytest.raises(HTTPException) as exc_info:
        await mcp_message(mock_request, init_request)
    assert exc_info.value.status_code == 404


async def test_sse_stores_capabilities_on_initialize() -> None:
    """Initialize request stores capabilities in the session."""
    session_id = "cap-session"
    queue: asyncio.Queue[str] = asyncio.Queue()
    _sessions[session_id] = Session(session_id=session_id, queue=queue)

    protocol, _registry = create_protocol_and_registry()

    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {"session_id": session_id}
    mock_request.app.state.protocol = protocol

    init_request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
        params={"capabilities": ["read_wallet", "preview_tx"]},
    )
    await mcp_message(mock_request, init_request)

    session = _sessions[session_id]
    assert session.capabilities == {"read_wallet", "preview_tx"}
