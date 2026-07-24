"""SSE transport tests."""

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from httpx import AsyncClient

from rustok_mcp.capabilities import Session
from rustok_mcp.config import clear_settings_cache
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcRequest
from rustok_mcp.sse import (
    MAX_SESSIONS,
    _sessions,
    mcp_message,
    mcp_sse,
    reap_stale_sessions,
)

_INIT_BODY = {"jsonrpc": "2.0", "method": "initialize", "id": 1}


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    """Remove test sessions between tests."""
    _sessions.clear()


def _set_inbound_key(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Configure (or clear) the inbound key and refresh the settings cache."""
    if value is None:
        monkeypatch.delenv("RUSTOK_MCP_INBOUND_API_KEY", raising=False)
    else:
        monkeypatch.setenv("RUSTOK_MCP_INBOUND_API_KEY", value)
    clear_settings_cache()


async def test_message_rejected_without_token_when_key_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /mcp/message without a bearer token returns 401 when a key is set."""
    _set_inbound_key(monkeypatch, "secret")
    response = await client.post("/mcp/message", json=_INIT_BODY)
    assert response.status_code == 401


async def test_message_accepts_valid_token_when_key_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid token passes auth — request reaches session lookup (404, not 401)."""
    _set_inbound_key(monkeypatch, "secret")
    response = await client.post(
        "/mcp/message",
        json=_INIT_BODY,
        headers={"Authorization": "Bearer secret"},
    )
    # 404 with the handler's own detail proves auth passed and the request
    # reached mcp_message's session lookup (not a routing 404 / 401).
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


async def test_message_rejects_non_bearer_scheme_when_key_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-Bearer scheme (e.g. Basic) is rejected with 401, not let through."""
    _set_inbound_key(monkeypatch, "secret")
    response = await client.post(
        "/mcp/message",
        json=_INIT_BODY,
        headers={"Authorization": "Basic c2VjcmV0"},
    )
    assert response.status_code == 401


async def test_message_open_when_key_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no key, the request passes auth and reaches session lookup (404)."""
    _set_inbound_key(monkeypatch, None)
    response = await client.post("/mcp/message", json=_INIT_BODY)
    assert response.status_code == 404


async def test_sse_get_rejected_without_token_when_key_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /mcp/sse is gated before streaming starts — 401 without a token."""
    _set_inbound_key(monkeypatch, "secret")
    response = await client.get("/mcp/sse")
    assert response.status_code == 401


async def test_sse_yields_endpoint_event() -> None:
    """The SSE stream starts with an endpoint event containing the session URI."""
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {}

    response = await mcp_sse(mock_request)
    assert response.media_type == "text/event-stream"

    body = ""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, str) else bytes(chunk).decode()
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
    assert data["result"]["protocolVersion"] == "2025-11-25"
    # The REAL SSE path shares the XOR guard: "error": null next to a result
    # is what a strict client rejects (the 2026-07-15 outage).
    assert "error" not in data


async def test_second_initialize_cannot_change_session_capabilities() -> None:
    """Capabilities are set on the FIRST initialize only: a standard MCP
    capabilities *object* (parses to empty) must not leave the session open
    to a second initialize granting a wider set."""
    session_id = "test-session-second-init"
    queue: asyncio.Queue[str] = asyncio.Queue()
    _sessions[session_id] = Session(session_id=session_id, queue=queue)

    protocol, _registry = create_protocol_and_registry()
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {"session_id": session_id}
    mock_request.app.state.protocol = protocol

    # First initialize with the standard MCP object — parses to the empty set.
    first = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
        params={"capabilities": {"roots": {}, "sampling": {}}},
    )
    await mcp_message(mock_request, first)
    assert _sessions[session_id].capabilities == set()

    # Second initialize tries to self-grant — must be ignored.
    second = JsonRpcRequest(
        jsonrpc="2.0",
        id=2,
        method="initialize",
        params={"capabilities": ["read_wallet", "execute_tx"]},
    )
    await mcp_message(mock_request, second)
    assert _sessions[session_id].capabilities == set()


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


async def test_sse_standard_capabilities_object_stays_gated() -> None:
    """A standard MCP capabilities object leaves the SSE session gated (0 tools)."""
    session_id = "gated-session"
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
        params={"capabilities": {"roots": {}, "sampling": {}}},
    )
    await mcp_message(mock_request, init_request)

    # Session is gated; tools/list should return 0 tools.
    list_response = await protocol.handle(
        JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list"),
        {"capabilities": _sessions[session_id].capabilities},
    )
    assert list_response is not None
    assert list_response.result["tools"] == []


async def test_sse_message_updates_last_seen() -> None:
    """POST /mcp/message refreshes the session's last_seen timestamp."""
    session_id = "active-session"
    queue: asyncio.Queue[str] = asyncio.Queue()
    _sessions[session_id] = Session(session_id=session_id, queue=queue)

    before = _sessions[session_id].last_seen
    time.sleep(0.01)

    protocol, _registry = create_protocol_and_registry()
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {"session_id": session_id}
    mock_request.app.state.protocol = protocol

    await mcp_message(
        mock_request,
        JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize"),
    )
    assert _sessions[session_id].last_seen > before


def test_reap_stale_sessions_evicts_only_idle() -> None:
    """reap_stale_sessions removes idle sessions and signals them to disconnect."""
    now = time.monotonic()
    fresh_queue: asyncio.Queue[str] = asyncio.Queue()
    stale_queue: asyncio.Queue[str] = asyncio.Queue()
    sessions: dict[str, Session] = {
        "fresh": Session(session_id="fresh", queue=fresh_queue, last_seen=now),
        "stale": Session(session_id="stale", queue=stale_queue, last_seen=now - 10_000),
    }

    evicted = reap_stale_sessions(sessions, now, ttl=600.0)

    assert evicted == ["stale"]
    assert "fresh" in sessions
    assert "stale" not in sessions
    assert stale_queue.get_nowait() == "__disconnect__"
    assert fresh_queue.empty()


async def test_sse_rejects_new_session_when_at_capacity() -> None:
    """GET /mcp/sse returns 503 when the session store is at MAX_SESSIONS."""
    for i in range(MAX_SESSIONS):
        _sessions[f"session-{i}"] = Session(session_id=f"session-{i}")

    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {}

    with pytest.raises(HTTPException) as exc_info:
        await mcp_sse(mock_request)
    assert exc_info.value.status_code == 503
    assert "too many sessions" in exc_info.value.detail
