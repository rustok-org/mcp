"""MCP handler tests."""

from typing import Any
from unittest.mock import AsyncMock

from rustok_mcp.capabilities import Capability
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcRequest


async def test_initialize_handler() -> None:
    """initialize returns protocol version and server info."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize")
    response = await protocol.handle(request)

    assert response is not None
    assert response.result is not None
    assert response.result["protocolVersion"] == "2024-11-05"
    assert response.result["serverInfo"]["name"] == "rustok-mcp"


async def test_initialize_stores_capabilities() -> None:
    """initialize parses and stores client capabilities in context."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, set[str]] = {}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
        params={"capabilities": ["read_wallet", "preview_tx"]},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert context["capabilities"] == {Capability.READ_WALLET, Capability.PREVIEW_TX}


async def test_tools_list_handler() -> None:
    """tools/list returns registered stub tools."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list")
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    tools = response.result["tools"]
    assert len(tools) == 5
    names = {t["name"] for t in tools}
    assert "get_wallet_context" in names
    assert "preview_send" in names


async def test_tools_list_filters_by_capability() -> None:
    """tools/list only returns tools allowed by session capabilities."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": {Capability.READ_WALLET}}
    request = JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list")
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    tools = response.result["tools"]
    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert "get_wallet_context" in names
    assert "get_balances" in names
    assert "preview_send" not in names


async def test_tools_list_denies_all_without_context() -> None:
    """tools/list without context returns empty list (fail-closed)."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list")
    response = await protocol.handle(request)

    assert response is not None
    assert response.result is not None
    assert response.result["tools"] == []


async def test_tools_call_handler_success() -> None:
    """tools/call executes a stub tool."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert response.result["content"][0]["type"] == "text"
    assert "0x0000000000000000000000000000000000000000" in response.result["content"][0]["text"]


async def test_tools_call_handler_missing_name() -> None:
    """tools/call without name returns Invalid Params."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"arguments": {}},
    )
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602


async def test_tools_call_handler_unknown_tool() -> None:
    """tools/call with unknown name returns error."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"name": "unknown_tool", "arguments": {}},
    )
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32001


async def test_tools_call_capability_denied() -> None:
    """tools/call without required capability returns authorization error."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": {Capability.READ_WALLET}}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"name": "execute_send", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32001
    assert "requires additional capability" in response.error.message


async def test_tools_call_capability_denied_without_context() -> None:
    """tools/call without context denies all mapped tools (fail-closed)."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32001


async def test_tools_call_serializes_non_dict_result() -> None:
    """Non-dict results are serialized as JSON, not str()."""
    protocol, registry = create_protocol_and_registry()

    async def _return_list(_args: dict[str, Any]) -> list[int]:
        return [1, 2, 3]

    # Re-register get_wallet_context with a list-returning handler
    tools = registry.list_tools()
    wallet_tool = next(t for t in tools if t.name == "get_wallet_context")
    registry.register(wallet_tool, _return_list)

    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=4,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert text == "[1, 2, 3]"


async def test_get_wallet_context_uses_gateway_client() -> None:
    """get_wallet_context tool delegates to GatewayClient when provided."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xreal",
            "balances": [{"chain_id": 1, "symbol": "ETH", "balance": "100"}],
            "allowed_chains": [1],
        },
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=15,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "0xreal" in response.result["content"][0]["text"]
    mock_client.wallet_context.assert_awaited_once_with()


async def test_get_wallet_context_falls_back_to_stub() -> None:
    """get_wallet_context returns zero-address stub without GatewayClient."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=15,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "0x0000000000000000000000000000000000000000" in response.result["content"][0]["text"]


async def test_get_balances_uses_gateway_client() -> None:
    """get_balances tool returns balances from wallet context."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xreal",
            "balances": [
                {"chain_id": 1, "symbol": "ETH", "balance": "100"},
                {"chain_id": 8453, "symbol": "ETH", "balance": "7"},
            ],
            "allowed_chains": [1, 8453],
        },
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=16,
        method="tools/call",
        params={"name": "get_balances", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert "8453" in text
    mock_client.wallet_context.assert_awaited_once_with()


async def test_get_balances_filters_by_chain_id() -> None:
    """get_balances applies the optional chain_id filter."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xreal",
            "balances": [
                {"chain_id": 1, "symbol": "ETH", "balance": "100"},
                {"chain_id": 8453, "symbol": "ETH", "balance": "7"},
            ],
            "allowed_chains": [1, 8453],
        },
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=17,
        method="tools/call",
        params={"name": "get_balances", "arguments": {"chain_id": 8453}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert "8453" in text
    assert '"chain_id": 1,' not in text


async def test_preview_send_uses_gateway_client() -> None:
    """preview_send tool delegates to GatewayClient when provided."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.preview_send = AsyncMock(return_value={"preview_id": "real-id"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=5,
        method="tools/call",
        params={
            "name": "preview_send",
            "arguments": {"to": "0xabc", "amount": "1.0", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "real-id" in response.result["content"][0]["text"]
    mock_client.preview_send.assert_awaited_once_with(to="0xabc", amount="1.0", chain_id=1)


async def test_preview_send_falls_back_to_stub() -> None:
    """preview_send tool returns stub when no GatewayClient is provided."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=5,
        method="tools/call",
        params={
            "name": "preview_send",
            "arguments": {"to": "0xabc", "amount": "1.0", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "stub-preview-id" in response.result["content"][0]["text"]


async def test_execute_send_uses_gateway_client() -> None:
    """execute_send tool delegates to GatewayClient when provided."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.execute_send = AsyncMock(return_value={"tx_hash": "0xreal"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=6,
        method="tools/call",
        params={"name": "execute_send", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "0xreal" in response.result["content"][0]["text"]
    mock_client.execute_send.assert_awaited_once_with(preview_id="abc")


async def test_sign_message_uses_gateway_client() -> None:
    """sign_message tool delegates to GatewayClient when provided."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.sign_message = AsyncMock(return_value={"signature": "0xreal"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=7,
        method="tools/call",
        params={"name": "sign_message", "arguments": {"message": "hello", "sign_type": "eip191"}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "0xreal" in response.result["content"][0]["text"]
    mock_client.sign_message.assert_awaited_once_with(message="hello", sign_type="eip191")


async def test_preview_send_missing_arg_returns_invalid_params() -> None:
    """Missing required argument maps to -32602 (Invalid params), not -32603."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=8,
        method="tools/call",
        params={
            "name": "preview_send",
            "arguments": {"amount": "1.0", "chain_id": 1},  # missing "to"
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "to" in response.error.message
    mock_client.preview_send.assert_not_awaited()


async def test_execute_send_missing_arg_returns_invalid_params() -> None:
    """execute_send without preview_id maps to -32602, Gateway not called."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=9,
        method="tools/call",
        params={"name": "execute_send", "arguments": {}},  # missing "preview_id"
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "preview_id" in response.error.message
    mock_client.execute_send.assert_not_awaited()


async def test_sign_message_missing_arg_returns_invalid_params() -> None:
    """sign_message without message maps to -32602, Gateway not called."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=10,
        method="tools/call",
        params={"name": "sign_message", "arguments": {"sign_type": "eip191"}},  # missing "message"
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "message" in response.error.message
    mock_client.sign_message.assert_not_awaited()
