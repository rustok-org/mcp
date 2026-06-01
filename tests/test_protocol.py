"""JSON-RPC protocol layer tests."""

from typing import Any

from rustok_mcp.protocol import JsonRpcRequest, McpError, McpProtocol


async def test_handle_unknown_method() -> None:
    """Unknown method must return Method Not Found error."""
    protocol = McpProtocol()
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="unknown")
    response = await protocol.handle(request)

    assert response is not None
    assert response.id == 1
    assert response.error is not None
    assert response.error.code == -32601


async def test_handle_notification_returns_none() -> None:
    """Notifications (no id, notifications/ prefix) return None."""
    protocol = McpProtocol()
    called = False

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> None:
        nonlocal called
        called = True

    protocol.register("notifications/initialized", handler)
    request = JsonRpcRequest(jsonrpc="2.0", method="notifications/initialized")
    response = await protocol.handle(request)

    assert response is None
    assert called is True


async def test_handle_notification_without_prefix() -> None:
    """Any request without id is a notification, regardless of method name."""
    protocol = McpProtocol()
    called = False

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> None:
        nonlocal called
        called = True

    protocol.register("some_method", handler)
    request = JsonRpcRequest(jsonrpc="2.0", method="some_method")
    response = await protocol.handle(request)

    assert response is None
    assert called is True


async def test_handle_successful_request() -> None:
    """Registered handler result is wrapped in JsonRpcResponse."""
    protocol = McpProtocol()

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> dict[str, str]:
        return {"status": "ok"}

    protocol.register("initialize", handler)
    request = JsonRpcRequest(jsonrpc="2.0", id=42, method="initialize")
    response = await protocol.handle(request)

    assert response is not None
    assert response.id == 42
    assert response.result == {"status": "ok"}
    assert response.error is None


async def test_handle_value_error() -> None:
    """ValueError from handler is mapped to Invalid Params."""
    protocol = McpProtocol()

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> None:
        raise ValueError("bad param")

    protocol.register("test", handler)
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="test")
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "bad param" in response.error.message


async def test_handle_generic_exception() -> None:
    """Unexpected exceptions are mapped to Internal Error."""
    protocol = McpProtocol()

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> None:
        raise RuntimeError("boom")

    protocol.register("test", handler)
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="test")
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32603
    assert "boom" in response.error.message


async def test_handle_passes_context() -> None:
    """Context dict is forwarded to the handler."""
    protocol = McpProtocol()
    received_context: dict[str, Any] | None = None

    async def handler(_req: JsonRpcRequest, ctx: dict[str, Any] | None = None) -> str:
        nonlocal received_context
        received_context = ctx
        return "ok"

    protocol.register("test", handler)
    context = {"key": "value"}
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="test")
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result == "ok"
    assert received_context == context


async def test_handle_mcperror_custom_code() -> None:
    """McpError carries a custom JSON-RPC error code."""
    protocol = McpProtocol()

    async def handler(_req: JsonRpcRequest, _ctx: dict[str, Any] | None = None) -> None:
        raise McpError(-32001, "Capability denied")

    protocol.register("test", handler)
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="test")
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32001
    assert "Capability denied" in response.error.message
