"""MCP JSON-RPC handlers and protocol wiring."""

import json
from typing import Any

from rustok_mcp.capabilities import (
    has_capability,
    parse_capabilities,
)
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.protocol import JsonRpcRequest, McpError, McpProtocol
from rustok_mcp.tools import Tool, ToolRegistry


def _serialize_result(result: Any) -> str:
    """Serialize a tool result to a JSON string."""
    try:
        return json.dumps(result)
    except (TypeError, ValueError):
        return str(result)


def _require(args: dict[str, Any], key: str) -> Any:
    """Return ``args[key]`` or raise ValueError (-> JSON-RPC -32602 Invalid params)."""
    try:
        return args[key]
    except KeyError as exc:
        raise ValueError(f"Missing required argument: {key}") from exc


async def handle_initialize(
    request: JsonRpcRequest,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle the ``initialize`` JSON-RPC method.

    Capabilities come from the rustok-specific ``params.capabilities`` *list*. A
    client that omits it — or sends the standard MCP capabilities *object* — keeps
    the transport-seeded default, so the process-trusted stdio transport (seeded
    with all capabilities) stays usable by standard MCP clients. A non-empty list
    overrides the default, letting a client opt into a narrower set.
    """
    params = request.params or {}
    if isinstance(params, dict) and context is not None:
        raw_caps = params.get("capabilities", [])
        caps = parse_capabilities(raw_caps) if isinstance(raw_caps, list) else set()
        if caps:
            context["capabilities"] = caps
        else:
            context.setdefault("capabilities", set())
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "rustok-mcp", "version": "0.1.0"},
    }


async def handle_tools_list(
    request: JsonRpcRequest,  # noqa: ARG001
    registry: ToolRegistry,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle the ``tools/list`` JSON-RPC method."""
    schemas = registry.get_tool_schemas()
    caps = context.get("capabilities", set()) if context else set()
    schemas = [s for s in schemas if has_capability(s["name"], caps)]
    return {"tools": schemas}


async def handle_tools_call(
    request: JsonRpcRequest,
    registry: ToolRegistry,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
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

    caps = context.get("capabilities", set()) if context else set()
    if not has_capability(name, caps):
        raise McpError(-32001, f"Tool '{name}' requires additional capability")

    result = await registry.call(name, arguments)
    return {
        "content": [
            {
                "type": "text",
                "text": _serialize_result(result),
            },
        ],
    }


def _make_get_wallet_context_handler(client: GatewayClient | None) -> Any:
    async def handler(_args: dict[str, Any]) -> Any:
        if client is None:
            return {
                "address": "0x0000000000000000000000000000000000000000",
                "balances": [],
            }
        return await client.wallet_context()

    return handler


def _make_get_balances_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"balances": []}
        address = args.get("address")
        chain_id = args.get("chain_id")
        if address is not None:
            # Explicit address — query a single chain via GET /wallet/balance.
            if chain_id is None:
                raise ValueError("Missing required argument: chain_id (required with address)")
            result = await client.get_balance(address, chain_id)
            return {
                "balances": [{"chain_id": chain_id, "balance": result.get("balance")}],
            }
        # Active wallet — balances come with the wallet context.
        context = await client.wallet_context()
        balances = context.get("balances", [])
        if chain_id is not None:
            balances = [b for b in balances if b.get("chain_id") == chain_id]
        return {"balances": balances}

    return handler


def _make_get_positions_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"positions": []}
        # Empty/omitted address → the active wallet's own positions.
        return await client.get_positions(args.get("address"))

    return handler


def _make_preview_send_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"preview_id": "stub-preview-id", "estimated_gas": "21000"}
        return await client.preview_send(
            to=_require(args, "to"),
            amount=_require(args, "amount"),
            chain_id=_require(args, "chain_id"),
        )

    return handler


def _make_execute_send_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"tx_hash": "0xstubtxhash"}
        return await client.execute_send(preview_id=_require(args, "preview_id"))

    return handler


def _make_sign_message_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"signature": "0xstubsignature"}
        return await client.sign_message(
            message=_require(args, "message"),
            sign_type=args.get("sign_type", "eip191"),
        )

    return handler


def create_protocol_and_registry(
    gateway_client: GatewayClient | None = None,
) -> tuple[McpProtocol, ToolRegistry]:
    """Wire handlers and tools into a protocol instance.

    Returns a tuple of ``(protocol, registry)`` ready to handle requests.
    """
    registry = ToolRegistry()
    protocol = McpProtocol()

    registry.register(
        Tool(
            name="get_wallet_context",
            description="Get the active wallet address and chain balances.",
            inputSchema={"type": "object", "properties": {}},
        ),
        _make_get_wallet_context_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="get_balances",
            description="Get token balances for the active wallet, or for an explicit address.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Optional address to query instead of the active wallet (requires chain_id)",
                    },
                    "chain_id": {
                        "type": "integer",
                        "description": "Chain ID: optional filter for the active wallet, required with address",
                    },
                },
            },
        ),
        _make_get_balances_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="get_positions",
            description="Get on-chain DeFi positions (Aave v3, ERC-4626) for the active wallet, or for an explicit address.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Optional address to query instead of the active wallet",
                    },
                },
            },
        ),
        _make_get_positions_handler(gateway_client),
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
        _make_preview_send_handler(gateway_client),
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
        _make_execute_send_handler(gateway_client),
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
        _make_sign_message_handler(gateway_client),
    )

    # Wire JSON-RPC handlers
    async def _tools_list_handler(
        req: JsonRpcRequest,
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await handle_tools_list(req, registry, ctx)

    async def _tools_call_handler(
        req: JsonRpcRequest,
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await handle_tools_call(req, registry, ctx)

    protocol.register("initialize", handle_initialize)
    protocol.register("tools/list", _tools_list_handler)
    protocol.register("tools/call", _tools_call_handler)

    return protocol, registry
