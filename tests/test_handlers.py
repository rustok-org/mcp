"""MCP handler tests."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

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
    assert response.result["protocolVersion"] == "2025-11-25"
    assert response.result["serverInfo"]["name"] == "rustok-mcp"


@pytest.mark.parametrize(
    "revision",
    ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"],
)
async def test_initialize_echoes_every_supported_protocol_revision(revision: str) -> None:
    """The live bug (first real user, 2026-07-15): Claude Code 2.1.2 asks for
    2025-11-25, a hard-pinned 2024-11-05 answer is silently rejected and the
    connection times out. The server must mirror a supported client revision."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(
        jsonrpc="2.0", id=1, method="initialize", params={"protocolVersion": revision}
    )
    response = await protocol.handle(request)
    assert response is not None and response.result is not None
    assert response.result["protocolVersion"] == revision


@pytest.mark.parametrize(
    "params",
    [
        None,  # no params at all
        {},  # params without the field
        {"protocolVersion": "1999-01-01"},  # unknown revision
        {"protocolVersion": 42},  # not a string
        ["not", "a", "dict"],  # list-shaped params
    ],
)
async def test_initialize_falls_back_to_the_newest_revision(params: object) -> None:
    """Anything we cannot honestly mirror gets our newest revision — per the
    MCP spec the client then decides whether to proceed."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize", params=params)
    response = await protocol.handle(request)
    assert response is not None and response.result is not None
    assert response.result["protocolVersion"] == "2025-11-25"


async def test_server_info_version_comes_from_package_metadata() -> None:
    """serverInfo must never lie about the shipped version again: the published
    v0.7.0 image reported 0.6.0 because the string lived in code, not metadata."""
    import importlib.metadata

    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize")
    response = await protocol.handle(request)
    assert response is not None and response.result is not None
    assert response.result["serverInfo"]["version"] == importlib.metadata.version("rustok-mcp")


async def test_wire_response_never_carries_both_result_and_error() -> None:
    """JSON-RPC 2.0: a response has EITHER `result` OR `error` — never both
    keys. `model_dump_json()` emitted `"error": null` next to every result,
    and Claude Code 2.1's strict parser silently rejects such a message (the
    second root of the first real user's 30 s timeout, 2026-07-15)."""
    protocol, _registry = create_protocol_and_registry()
    ok = await protocol.handle(JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize", params={}))
    assert ok is not None
    ok_wire = json.loads(ok.to_wire())
    assert "result" in ok_wire and "error" not in ok_wire, ok.to_wire()

    err = await protocol.handle(JsonRpcRequest(jsonrpc="2.0", id=2, method="no/such/method"))
    assert err is not None
    err_wire = json.loads(err.to_wire())
    assert "error" in err_wire and "result" not in err_wire, err.to_wire()


async def test_initialize_includes_welcome_instructions() -> None:
    """initialize returns mission/safety/donation instructions for the LLM."""
    protocol, _registry = create_protocol_and_registry()
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize")
    response = await protocol.handle(request)

    assert response is not None
    assert response.result is not None
    instructions = response.result["instructions"]
    assert isinstance(instructions, str)
    assert instructions
    assert "0xA713e7145F0060A35E92a928e997B42481c0FfEE" in instructions
    assert "self-custody" in instructions.lower()
    assert "preview" in instructions.lower()


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


async def test_initialize_keeps_seeded_default_for_object() -> None:
    """A standard MCP capabilities *object* must not wipe the seeded default."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, Any] = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
        params={"capabilities": {"roots": {}, "sampling": {}}},
    )
    await protocol.handle(request, context)
    assert context["capabilities"] == set(Capability)


async def test_initialize_keeps_seeded_default_when_absent() -> None:
    """No capabilities field keeps the seeded default (stdio stays usable)."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, Any] = {"capabilities": set(Capability)}
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize")
    await protocol.handle(request, context)
    assert context["capabilities"] == set(Capability)


async def test_initialize_list_overrides_seeded_default() -> None:
    """An explicit rustok list narrows the seeded default."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, Any] = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="initialize",
        params={"capabilities": ["read_wallet"]},
    )
    await protocol.handle(request, context)
    assert context["capabilities"] == {Capability.READ_WALLET}


async def test_initialize_empty_context_defaults_to_empty_set() -> None:
    """With no seed and no caps, context defaults to an empty (gated) set."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, Any] = {}
    request = JsonRpcRequest(jsonrpc="2.0", id=1, method="initialize")
    await protocol.handle(request, context)
    assert context["capabilities"] == set()


async def test_tools_list_handler() -> None:
    """tools/list returns registered stub tools."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list")
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    tools = response.result["tools"]
    assert len(tools) == 7
    names = {t["name"] for t in tools}
    assert "get_wallet_context" in names
    assert "get_positions" in names
    assert "preview_transaction" in names
    assert "execute_transaction" in names
    assert "get_execution_status" in names


async def test_tools_list_filters_by_capability() -> None:
    """tools/list only returns tools allowed by session capabilities."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": {Capability.READ_WALLET}}
    request = JsonRpcRequest(jsonrpc="2.0", id=2, method="tools/list")
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    tools = response.result["tools"]
    assert len(tools) == 3
    names = {t["name"] for t in tools}
    assert "get_wallet_context" in names
    assert "get_balances" in names
    assert "get_positions" in names
    assert "preview_transaction" not in names


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
        params={"name": "sign_message", "arguments": {"message": "x", "sign_type": "eip191"}},
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


async def test_get_balances_with_address_uses_balance_endpoint() -> None:
    """get_balances with an explicit address queries /wallet/balance."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_balance = AsyncMock(return_value={"balance": "42"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=18,
        method="tools/call",
        params={
            "name": "get_balances",
            "arguments": {"address": "0xabc", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "42" in response.result["content"][0]["text"]
    mock_client.get_balance.assert_awaited_once_with("0xabc", 1)
    mock_client.wallet_context.assert_not_awaited()


async def test_get_balances_address_without_chain_id_is_invalid() -> None:
    """get_balances with address but no chain_id returns invalid params."""
    mock_client = AsyncMock(spec=GatewayClient)

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=19,
        method="tools/call",
        params={"name": "get_balances", "arguments": {"address": "0xabc"}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "chain_id" in response.error.message


async def test_get_positions_uses_gateway_client() -> None:
    """get_positions (no address) delegates to the active wallet."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_positions = AsyncMock(
        return_value={
            "positions": [
                {"protocol": "aave_v3", "chain_id": 1, "asset_symbol": "USD"},
            ],
        },
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=20,
        method="tools/call",
        params={"name": "get_positions", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "aave_v3" in response.result["content"][0]["text"]
    mock_client.get_positions.assert_awaited_once_with(None)


async def test_get_positions_with_explicit_address() -> None:
    """get_positions forwards an explicit address to the Gateway."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_positions = AsyncMock(return_value={"positions": []})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=21,
        method="tools/call",
        params={"name": "get_positions", "arguments": {"address": "0xabc"}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    mock_client.get_positions.assert_awaited_once_with("0xabc")


async def test_get_positions_falls_back_to_stub() -> None:
    """get_positions returns an empty list without a GatewayClient."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=22,
        method="tools/call",
        params={"name": "get_positions", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert '"positions": []' in response.result["content"][0]["text"]


async def test_preview_transaction_uses_gateway_client() -> None:
    """preview_transaction tool delegates to GatewayClient when provided."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.preview_transaction = AsyncMock(return_value={"preview_id": "real-id"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=5,
        method="tools/call",
        params={
            "name": "preview_transaction",
            "arguments": {"to": "0xabc", "value": "1.0", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "real-id" in response.result["content"][0]["text"]
    mock_client.preview_transaction.assert_awaited_once_with(
        to="0xabc", value="1.0", chain_id=1, data=""
    )


async def test_preview_transaction_falls_back_to_stub() -> None:
    """preview_transaction tool returns stub when no GatewayClient is provided."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=5,
        method="tools/call",
        params={
            "name": "preview_transaction",
            "arguments": {"to": "0xabc", "value": "1.0", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    assert "stub-preview-id" in response.result["content"][0]["text"]


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


async def test_preview_transaction_missing_arg_returns_invalid_params() -> None:
    """Missing required argument maps to -32602 (Invalid params), not -32603."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=8,
        method="tools/call",
        params={
            "name": "preview_transaction",
            "arguments": {"value": "1.0", "chain_id": 1},  # missing "to"
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "to" in response.error.message
    mock_client.preview_transaction.assert_not_awaited()


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


def _tool_result(response: Any) -> Any:
    """Parse the JSON payload out of a tools/call text response."""
    assert response is not None
    assert response.result is not None
    return json.loads(response.result["content"][0]["text"])


async def test_execute_transaction_uses_gateway_client() -> None:
    """execute_transaction tool delegates to GatewayClient and forwards the response."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.execute_transaction = AsyncMock(
        return_value={
            "state": "pending",
            "tx_hash": None,
            "error_reason": None,
            "not_after_unix": 1780000000,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=11,
        method="tools/call",
        params={"name": "execute_transaction", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result["state"] == "pending"
    assert result["not_after_unix"] == 1780000000
    mock_client.execute_transaction.assert_awaited_once_with(preview_id="abc")


async def test_execute_transaction_pending_carries_next_step() -> None:
    """A parked execution tells the human where to approve — console command included."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.execute_transaction = AsyncMock(
        return_value={
            "state": "pending",
            "tx_hash": None,
            "error_reason": None,
            "not_after_unix": 1780000000,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=12,
        method="tools/call",
        params={"name": "execute_transaction", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert "docker exec -it rustok-wallet-tui rustok-console" in result["next_step"]


async def test_execute_transaction_missing_arg_returns_invalid_params() -> None:
    """execute_transaction without preview_id maps to -32602, Gateway not called."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=13,
        method="tools/call",
        params={"name": "execute_transaction", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "preview_id" in response.error.message
    mock_client.execute_transaction.assert_not_awaited()


async def test_execute_transaction_falls_back_to_stub() -> None:
    """execute_transaction without a GatewayClient returns a pending stub, no next_step."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=14,
        method="tools/call",
        params={"name": "execute_transaction", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result["state"] == "pending"
    assert "next_step" not in result


async def test_get_execution_status_uses_gateway_client() -> None:
    """get_execution_status forwards a terminal response untouched — no next_step."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_execution_status = AsyncMock(
        return_value={
            "state": "executed",
            "tx_hash": "0xhash",
            "error_reason": None,
            "not_after_unix": None,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=15,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result == {
        "state": "executed",
        "tx_hash": "0xhash",
        "error_reason": None,
        "not_after_unix": None,
    }
    mock_client.get_execution_status.assert_awaited_once_with(preview_id="abc")


async def test_get_execution_status_pending_carries_next_step() -> None:
    """A still-pending status reminds the human where the approval console is."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_execution_status = AsyncMock(
        return_value={
            "state": "pending",
            "tx_hash": None,
            "error_reason": None,
            "not_after_unix": 1780000000,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=16,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert "docker exec -it rustok-wallet-tui rustok-console" in result["next_step"]


async def test_get_execution_status_missing_arg_returns_invalid_params() -> None:
    """get_execution_status without preview_id maps to -32602, Gateway not called."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=17,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "preview_id" in response.error.message
    mock_client.get_execution_status.assert_not_awaited()


async def test_execution_status_unknown_state_is_not_terminal_no_next_step() -> None:
    """An 'unknown' state (proto drift) passes through without the pending hint."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_execution_status = AsyncMock(
        return_value={
            "state": "unknown",
            "tx_hash": None,
            "error_reason": None,
            "not_after_unix": 1780000000,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=22,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result["state"] == "unknown"
    assert "next_step" not in result


async def test_execution_result_without_state_key_passes_through() -> None:
    """A dict payload lacking 'state' is forwarded as-is — no crash, no hint."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_execution_status = AsyncMock(return_value={"tx_hash": "0xhash"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=23,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result == {"tx_hash": "0xhash"}


async def test_execution_result_non_dict_passes_through_unchanged() -> None:
    """A malformed (non-dict) gateway payload is forwarded as-is, not crashed on."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_execution_status = AsyncMock(return_value=["unexpected", "payload"])

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=21,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result == ["unexpected", "payload"]


async def test_get_execution_status_falls_back_to_stub() -> None:
    """get_execution_status without a GatewayClient returns a pending stub, no next_step."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=18,
        method="tools/call",
        params={"name": "get_execution_status", "arguments": {"preview_id": "abc"}},
    )
    response = await protocol.handle(request, context)

    result = _tool_result(response)
    assert result["state"] == "pending"
    assert "next_step" not in result


async def test_execute_tools_hidden_without_execute_tx_capability() -> None:
    """Without execute_tx the new tools are neither listed nor callable."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": {Capability.READ_WALLET, Capability.PREVIEW_TX}}

    list_request = JsonRpcRequest(jsonrpc="2.0", id=19, method="tools/list")
    list_response = await protocol.handle(list_request, context)
    assert list_response is not None
    assert list_response.result is not None
    names = {t["name"] for t in list_response.result["tools"]}
    assert "execute_transaction" not in names
    assert "get_execution_status" not in names

    call_request = JsonRpcRequest(
        jsonrpc="2.0",
        id=20,
        method="tools/call",
        params={"name": "execute_transaction", "arguments": {"preview_id": "abc"}},
    )
    call_response = await protocol.handle(call_request, context)
    assert call_response is not None
    assert call_response.error is not None
    assert call_response.error.code == -32001
