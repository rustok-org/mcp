"""MCP JSON-RPC handlers and protocol wiring."""

import json
from typing import Any

from rustok_mcp.protocol import JsonRpcRequest, McpProtocol
from rustok_mcp.tools import Tool, ToolRegistry


def _serialize_result(result: Any) -> str:
    """Serialize a tool result to a JSON string."""
    try:
        return json.dumps(result)
    except (TypeError, ValueError):
        return str(result)


async def handle_initialize(request: JsonRpcRequest) -> dict[str, Any]:  # noqa: ARG001
    """Handle the ``initialize`` JSON-RPC method."""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "rustok-mcp", "version": "0.1.0"},
    }


async def handle_tools_list(request: JsonRpcRequest, registry: ToolRegistry) -> dict[str, Any]:  # noqa: ARG001
    """Handle the ``tools/list`` JSON-RPC method."""
    return {"tools": registry.get_tool_schemas()}


async def handle_tools_call(request: JsonRpcRequest, registry: ToolRegistry) -> dict[str, Any]:
    """Handle the ``tools/call`` JSON-RPC method."""
    params = request.params or {}
    if not isinstance(params, dict):
        raise ValueError("tools/call params must be an object")

    name = params.get("name")
    arguments = params.get("arguments", {})

    if not name:
        raise ValueError("Missing 'name' in tools/call params")
    if not isinstance(arguments, dict):
        raise ValueError("tools/call arguments must be an object")

    result = await registry.call(name, arguments)
    return {
        "content": [
            {
                "type": "text",
                "text": _serialize_result(result),
            },
        ],
    }


async def _stub_get_wallet_context(_args: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": "0x0000000000000000000000000000000000000000",
        "balances": [],
    }


async def _stub_get_balances(_args: dict[str, Any]) -> dict[str, Any]:
    return {"balances": []}


async def _stub_preview_send(_args: dict[str, Any]) -> dict[str, str]:
    return {"preview_id": "stub-preview-id", "estimated_gas": "21000"}


async def _stub_execute_send(_args: dict[str, Any]) -> dict[str, str]:
    return {"tx_hash": "0xstubtxhash"}


async def _stub_sign_message(_args: dict[str, Any]) -> dict[str, str]:
    return {"signature": "0xstubsignature"}


def create_protocol_and_registry() -> tuple[McpProtocol, ToolRegistry]:
    """Wire handlers and stub tools into a protocol instance.

    Returns a tuple of ``(protocol, registry)`` ready to handle requests.
    """
    registry = ToolRegistry()
    protocol = McpProtocol()

    # Register stub tools (Gateway integration comes in PR-3.4)
    registry.register(
        Tool(
            name="get_wallet_context",
            description="Get the active wallet address and chain balances.",
            inputSchema={"type": "object", "properties": {}},
        ),
        _stub_get_wallet_context,
    )
    registry.register(
        Tool(
            name="get_balances",
            description="Get token balances for the active wallet.",
            inputSchema={"type": "object", "properties": {}},
        ),
        _stub_get_balances,
    )
    registry.register(
        Tool(
            name="preview_send",
            description="Preview an ETH send transaction before executing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient address"},
                    "amount": {"type": "string", "description": "Amount in ETH"},
                    "chain_id": {"type": "integer", "description": "Chain ID"},
                },
                "required": ["to", "amount", "chain_id"],
            },
        ),
        _stub_preview_send,
    )
    registry.register(
        Tool(
            name="execute_send",
            description="Execute a previously previewed send transaction.",
            inputSchema={
                "type": "object",
                "properties": {
                    "preview_id": {"type": "string", "description": "Preview ID from preview_send"},
                },
                "required": ["preview_id"],
            },
        ),
        _stub_execute_send,
    )
    registry.register(
        Tool(
            name="sign_message",
            description="Sign a message with the active wallet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "sign_type": {"type": "string", "enum": ["eip191", "eip712"]},
                },
                "required": ["message"],
            },
        ),
        _stub_sign_message,
    )

    # Wire JSON-RPC handlers
    protocol.register("initialize", handle_initialize)
    protocol.register("tools/list", lambda req: handle_tools_list(req, registry))
    protocol.register("tools/call", lambda req: handle_tools_call(req, registry))

    return protocol, registry
