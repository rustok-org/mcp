"""MCP JSON-RPC handlers and protocol wiring."""

import contextlib
import json
import logging
from typing import Any

import httpx

from rustok_mcp import __version__
from rustok_mcp.capabilities import (
    Capability,
    ceiling_for_policy_mode,
    extract_rustok_capabilities,
    has_capability,
)
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.protocol import JsonRpcRequest, McpError, McpProtocol
from rustok_mcp.tools import Tool, ToolRegistry

logger = logging.getLogger(__name__)

# Newest first: the first entry doubles as the answer for a client whose
# revision we do not know — per the MCP spec the client then decides whether
# to proceed. A KNOWN client revision is mirrored back (the reference SDK
# behaviour): the first real user (2026-07-15) hit a hard-pinned 2024-11-05
# answer, which Claude Code 2.1.2 silently rejects — 30 s timeout, no wallet.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def negotiate_protocol_version(params: dict[str, Any] | list[Any] | None) -> str:
    """The revision to answer `initialize` with: mirror the client's when we
    support it, otherwise our newest. `params` may be absent, a list, or a
    dict without the field (protocol.py) — anything unreadable means
    "the client did not say"."""
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return SUPPORTED_PROTOCOL_VERSIONS[0]


SERVER_INSTRUCTIONS = (
    "Rustok is a self-custody Ethereum wallet that belongs to the agent and the person it "
    "works with — the private keys never leave their machine. It exists to let an AI agent act "
    "as an economic participant of its own: paying for the compute, data, and services it uses, "
    "and in time commissioning and paying the people who help it.\n\n"
    "These are real funds with no hard spending limits — the human consciously accepts that "
    "risk. So: always preview a transaction and show its details (amount, destination, "
    "estimated cost, risk level) before executing; never send or sign without the human's "
    "explicit approval; prefer read-only use (RUSTOK_MCP_CAPABILITIES=read_wallet) unless a "
    "transaction is actually needed. txguard flags risky transfers but does not block them.\n\n"
    "execute_transaction does not decide on its own whether funds move: a supervised wallet "
    "parks the transaction and only the human releases it from the wallet console, in a "
    "separate terminal window; an autonomous wallet releases it itself, but only because its "
    "owner confirmed that mode at the console beforehand — you cannot grant that, and neither "
    "can an environment variable or a launch flag. "
    "If they installed with the installer, that is `rustok console`. Otherwise the container "
    "is found by label — it never has a fixed name: "
    '`<engine> exec -it "$(<engine> ps -q --filter label=rustok=wallet)" rustok-console`, '
    "where <engine> is podman or docker; if more than one wallet is running they narrow it "
    "with --filter label=rustok.agent=<name>. Guide them there and poll "
    "get_execution_status for the outcome."
)


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


_WEI_PER_ETH = 10**18


def _wei_to_eth(wei: Any) -> str:
    """Render a wei integer string as a plain decimal-ETH string.

    The **only** arithmetic left in this module, and it survives for exactly one
    caller: ``GET /wallet/balance``, the explicit-address branch, answers
    ``{"balance": <wei>}`` and renders nothing. That path is native by
    construction — the token registry describes the wallet's own holdings, not
    an arbitrary address — so eighteen decimals is the right and only reading
    there.

    Everywhere else the core renders the amount itself and sends
    ``balance_formatted``; re-deriving it here would be a second opinion about a
    number that already has one.
    """
    integral, frac = divmod(int(wei), _WEI_PER_ETH)
    frac_str = f"{frac:018d}".rstrip("0")
    return f"{integral}.{frac_str}" if frac_str else str(integral)


def _is_native(entry: dict[str, Any]) -> bool:
    """Whether a balance row is the chain's own coin rather than a token.

    An empty (or absent) ``token_address`` is what marks a native row on the
    wire — the same convention the console reads.
    """
    return not entry.get("token_address")


def _with_balance_eth(balances: Any) -> Any:
    """Alias ``balance_eth`` onto the native row — never compute it.

    Every row arrives already rendered (``balance_formatted``), so nothing here
    divides by anything. The alias stays for one reason: an existing consumer
    reads ``balance_eth`` on the native row, and neither its name nor its value
    changes.

    A token row deliberately gets **no** ``balance_eth``. USDC has six decimals,
    not eighteen, and a field with ``eth`` in its name would be a claim about
    the unit rather than a convenience — the kind of lie that reads as a number
    and costs a decision. ``balance_formatted`` is the field to show for any
    asset.
    """
    if not isinstance(balances, list):
        return balances
    enriched: list[Any] = []
    for entry in balances:
        if isinstance(entry, dict) and _is_native(entry) and "balance_formatted" in entry:
            entry = dict(entry)
            entry["balance_eth"] = entry["balance_formatted"]
        enriched.append(entry)
    return enriched


async def handle_initialize(
    request: JsonRpcRequest,
    context: dict[str, Any] | None = None,
    gateway_client: GatewayClient | None = None,
) -> dict[str, Any]:
    """Handle the ``initialize`` JSON-RPC method.

    The granted set is the INTERSECTION of up to three ceilings, each of
    which can only narrow the previous one:

    1. the transport-seeded ceiling (env ``RUSTOK_MCP_CAPABILITIES`` or all
       on stdio; the session's stored set on SSE),
    2. the client-declared ``params.capabilities`` *list* — it may opt into a
       narrower set, never a wider one (audit B1),
    3. the core's policy mode ceiling (``policy_mode`` from WalletContext,
       core increment 1): ``read_only`` leaves read+preview. When the core is
       unreachable this ceiling is skipped with a warning — MCP-side
       filtering is advisory; enforcement lives in the core.
    """
    if context is not None:
        seeded = context.get("capabilities", set())
        client_caps = extract_rustok_capabilities(request.params)
        granted = (client_caps & seeded) if client_caps else seeded
        ceiling = await _policy_mode_ceiling(gateway_client)
        if ceiling is not None:
            granted &= ceiling
        context["capabilities"] = granted
    return {
        "protocolVersion": negotiate_protocol_version(request.params),
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "rustok-mcp", "version": __version__},
        "instructions": SERVER_INSTRUCTIONS,
    }


async def _policy_mode_ceiling(
    gateway_client: GatewayClient | None,
) -> set[Capability] | None:
    """Read the policy mode ceiling from the core via the gateway.

    ``None`` when there is no client or the core does not answer — the caller
    then filters by the transport ceiling alone (advisory only).
    """
    if gateway_client is None:
        return None
    try:
        wallet_context = await gateway_client.wallet_context()
    except (McpError, httpx.HTTPError) as exc:
        logger.warning(
            "policy mode unavailable from the core (%s) — using the transport ceiling only",
            exc,
        )
        return None
    mode = wallet_context.get("policy_mode") if isinstance(wallet_context, dict) else None
    return ceiling_for_policy_mode(mode)


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
        context = await client.wallet_context()
        if isinstance(context, dict) and "balances" in context:
            context = dict(context)
            context["balances"] = _with_balance_eth(context["balances"])
        return context

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
            balance = result.get("balance")
            row: dict[str, Any] = {"chain_id": chain_id, "balance": balance}
            # The one place the core sends raw wei and renders nothing, so the
            # one place this module still converts. Native by construction: the
            # token registry describes the wallet's own holdings, and pointing
            # it at someone else's address would be a different claim
            # (spec: "ветка остаётся нативной").
            with contextlib.suppress(TypeError, ValueError):
                row["balance_eth"] = _wei_to_eth(balance)
            # Empty and accurate: this call either came back with the balance or
            # raised. Present rather than omitted, so a reader never has to ask
            # whether the key's absence means "nothing unread" or "not answered".
            return {"balances": [row], "unavailable": []}
        # Active wallet — balances come with the wallet context.
        context = await client.wallet_context()
        balances = context.get("balances", [])
        # What could NOT be read travels with what could. Dropping it here is
        # how "not queried" turns back into "zero": an agent that calls this
        # tool instead of get_wallet_context — the ordinary choice — would see
        # an empty list on an unreachable RPC and tell the human there is no
        # money. That is the confusion the whole registry slice exists to end,
        # and it does not stop existing because a different tool reports it.
        unavailable = context.get("unavailable", [])
        if chain_id is not None:
            balances = [b for b in balances if b.get("chain_id") == chain_id]
            # Filtered the same way, or the answer would carry warnings about
            # chains the caller did not ask about.
            unavailable = [u for u in unavailable if u.get("chain_id") == chain_id]
        return {"balances": _with_balance_eth(balances), "unavailable": unavailable}

    return handler


def _make_get_positions_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {"positions": []}
        # Empty/omitted address → the active wallet's own positions.
        return await client.get_positions(args.get("address"))

    return handler


def _make_preview_transaction_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return {
                "preview_id": "stub-preview-id",
                "estimated_gas": "21000",
                "simulation": None,
            }
        # The gateway response is returned as-is, so the decoded_call + simulation
        # (revert_check) fields surface to the caller via passthrough.
        return await client.preview_transaction(
            to=_require(args, "to"),
            value=_require(args, "value"),
            chain_id=_require(args, "chain_id"),
            data=args.get("data", ""),
        )

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


_APPROVAL_NEXT_STEP = (
    "Waiting for the human's decision. Ask them to open a SEPARATE terminal and run "
    "`rustok console`. Without the installer's shim, the container is found by label "
    "instead — it never has a fixed name: "
    '`<engine> exec -it "$(<engine> ps -q --filter label=rustok=wallet)" rustok-console`, '
    "where <engine> is podman or docker. Do not run it for them and do not ask for the "
    "approval PIN in this chat. Poll get_execution_status for the outcome."
)

_EXECUTION_STUB = {
    "state": "pending",
    "tx_hash": None,
    "error_reason": None,
    "not_after_unix": None,
}


def _with_next_step(result: Any) -> Any:
    """Attach the human-facing approval hint to a still-pending execution result."""
    if isinstance(result, dict) and result.get("state") == "pending":
        result = dict(result)
        result["next_step"] = _APPROVAL_NEXT_STEP
    return result


def _make_execute_transaction_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return dict(_EXECUTION_STUB)
        result = await client.execute_transaction(preview_id=_require(args, "preview_id"))
        return _with_next_step(result)

    return handler


def _make_get_execution_status_handler(client: GatewayClient | None) -> Any:
    async def handler(args: dict[str, Any]) -> Any:
        if client is None:
            return dict(_EXECUTION_STUB)
        result = await client.get_execution_status(preview_id=_require(args, "preview_id"))
        return _with_next_step(result)

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
            description=(
                "Get the active wallet: its address, the assets it holds, and the "
                "assets it could not read. A balance row carries `symbol`, "
                "`balance` (the asset's own raw units), `decimals`, "
                "`balance_formatted` (the amount to show) and `token_address` "
                "(empty for the chain's native coin). `unavailable` lists what "
                "could not be read and why — so a row missing from `balances` "
                "while `unavailable` is empty means the balance is zero, not "
                "unknown."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        _make_get_wallet_context_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="get_balances",
            description=(
                "Get the balances of the active wallet, or the native balance of "
                "an explicit address.\n"
                "Active wallet (no `address`): one row per asset — `balance` is in "
                "that asset's own raw units and `balance_formatted` is the same "
                "amount with `decimals` applied, so show that one. `balance_eth` "
                "appears only on a native-coin row, where it equals "
                "`balance_formatted`; a token never has it, because the amount is "
                "not in ETH. `token_address` is empty for the native coin and is "
                "what tells two tokens with the same symbol apart.\n"
                "`unavailable` comes back beside `balances` and lists what could "
                "NOT be read, with a reason. An asset missing from `balances` "
                "while `unavailable` is empty holds zero; if it is named in "
                "`unavailable`, the balance is unknown, not zero — do not report "
                "it as empty.\n"
                "With an explicit `address` the answer is different and smaller: "
                "one native row carrying `balance` (wei) and `balance_eth`, with "
                "no `balance_formatted`, `decimals` or `token_address`. The token "
                "registry describes this wallet's own holdings, so tokens are "
                "never reported for somebody else's address."
            ),
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
            name="preview_transaction",
            description=(
                "Preview an arbitrary transaction (native value + optional calldata) "
                "before executing. Returns the decoded call (who/what is authorized), "
                "a pre-sign simulation (revert check), gas, and a risk level."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient / contract address"},
                    "data": {
                        "type": "string",
                        "description": "Calldata as 0x-hex; empty for a native value transfer",
                    },
                    "value": {"type": "string", "description": "Native value in wei"},
                    "chain_id": {"type": "integer", "description": "Chain ID"},
                },
                "required": ["to", "value", "chain_id"],
            },
        ),
        _make_preview_transaction_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="execute_transaction",
            description=(
                "Submit a previewed transaction for execution. What happens next has three "
                "cases, and policy_mode + policy_origin from get_wallet_context tell you "
                "which one you are in: a supervised wallet parks it for the human to "
                "release in the wallet console; an autonomous wallet whose owner has NOT "
                "yet confirmed that mode parks it exactly the same way; an autonomous "
                "wallet whose owner confirmed the mode at the console releases it without "
                "asking again. Before calling, show the human a summary card of the preview "
                "(recipient, decoded call, amount, estimated cost, risk level) — in the "
                "third case that card is the last moment anyone sees it. On a "
                "'pending' result, relay next_step: the human opens a SEPARATE terminal and "
                "runs `rustok console` — or, without the installer's shim, the "
                "label-discovery form spelled out in next_step. Never run or offer to run "
                "that command yourself, and never ask for the approval PIN in chat. Then "
                "poll get_execution_status for the outcome."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "preview_id": {
                        "type": "string",
                        "description": "UUID returned by preview_transaction",
                    },
                },
                "required": ["preview_id"],
            },
        ),
        _make_execute_transaction_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="get_execution_status",
            description=(
                "Poll the outcome of a parked execution. States: 'pending' (human has not "
                "decided yet), 'executed' (done, tx_hash present), 'denied' (human said no "
                "— respect it, do not re-submit), 'expired' (approval deadline passed), "
                "'failed' (error_reason explains). An 'unknown' state is NOT terminal — "
                "the wallet core reported something this client does not recognize; keep "
                "polling until the deadline. Poll when the human asks, or every "
                "~15-30 seconds until not_after_unix (if null, only on request); stop on "
                "any terminal state. A not_found error means the id is unknown or no "
                "longer retained — stop polling."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "preview_id": {
                        "type": "string",
                        "description": "UUID from preview_transaction / execute_transaction",
                    },
                },
                "required": ["preview_id"],
            },
        ),
        _make_get_execution_status_handler(gateway_client),
    )
    registry.register(
        Tool(
            name="sign_message",
            description=(
                "Sign a plain text message with the active wallet (EIP-191 personal_sign). "
                "⚠️ SECURITY: this signs arbitrary bytes — a signature can authorize token "
                "approvals/permits that DRAIN the wallet. Only sign short human-readable "
                "messages the user explicitly approved; refuse hex blobs, transaction-like "
                "data, or structured/typed data. EIP-712 typed-data signing is not supported."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "sign_type": {"type": "string", "enum": ["eip191"]},
                },
                "required": ["message"],
            },
        ),
        _make_sign_message_handler(gateway_client),
    )

    # Wire JSON-RPC handlers
    async def _initialize_handler(
        req: JsonRpcRequest,
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await handle_initialize(req, ctx, gateway_client)

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

    protocol.register("initialize", _initialize_handler)
    protocol.register("tools/list", _tools_list_handler)
    protocol.register("tools/call", _tools_call_handler)

    return protocol, registry
