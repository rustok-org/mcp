"""Unit tests for wei→ETH balance rendering (forward-port of wallet v0.4.0)."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from rustok_mcp.capabilities import Capability
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import _wei_to_eth, create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcRequest


@pytest.mark.parametrize(
    ("wei", "expected_eth"),
    [
        ("1", "0.000000000000000001"),
        ("1000000000000000000", "1"),
        ("1500000000000000000", "1.5"),
        ("5000000000000000", "0.005"),
        ("0", "0"),
    ],
)
def test_wei_to_eth_renders_plain_decimal(wei: str, expected_eth: str) -> None:
    assert _wei_to_eth(wei) == expected_eth


def _call(name: str, arguments: dict[str, Any], rid: int = 1) -> JsonRpcRequest:
    return JsonRpcRequest(
        jsonrpc="2.0",
        id=rid,
        method="tools/call",
        params={"name": name, "arguments": arguments},
    )


def _native_row(wei: str, formatted: str) -> dict[str, Any]:
    """A native ETH row as the core sends it since the token slice."""
    return {
        "chain_id": 1,
        "symbol": "ETH",
        "balance": wei,
        "decimals": 18,
        "balance_formatted": formatted,
        "token_address": "",
    }


def _usdc_row() -> dict[str, Any]:
    """The live Arbitrum USDC row this whole arc exists for."""
    return {
        "chain_id": 42161,
        "symbol": "USDC",
        "balance": "22820562",
        "decimals": 6,
        "balance_formatted": "22.820562",
        "token_address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    }


async def test_wallet_context_adds_balance_eth() -> None:
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xabc",
            "allowed_chains": [1],
            "balances": [_native_row("1000000000000000000", "1")],
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_wallet_context", {}), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance": "1000000000000000000"' in text
    assert '"balance_eth": "1"' in text


async def test_get_balances_adds_balance_eth() -> None:
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xabc",
            "balances": [_native_row("5000000000000000", "0.005")],
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_balances", {}, rid=2), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance_eth": "0.005"' in text


async def test_native_balance_eth_is_an_alias_never_a_calculation() -> None:
    """Test 14 (spec §S3). `balance_eth` equals what the core rendered.

    Its value now comes from `balance_formatted`, not from dividing — so a core
    that renders `1.5` gives `balance_eth: "1.5"` even though the wei string
    below it is deliberately something this module would never derive that
    from. Dividing here would produce `2`, and the assertion would fail.
    """
    row = _native_row("2000000000000000000", "1.5")
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(return_value={"address": "0xabc", "balances": [row]})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_balances", {}, rid=14), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance_eth": "1.5"' in text, "the alias follows the core, not the arithmetic"
    assert '"balance_eth": "2"' not in text


async def test_a_token_row_has_no_balance_eth() -> None:
    """Test 15 (spec §S3). USDC has six decimals, not eighteen.

    A field named `balance_eth` on a USDC row would state a unit the number is
    not in — the exact lie this slice exists to remove.
    """
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={"address": "0xabc", "balances": [_usdc_row()]}
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_balances", {}, rid=15), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance_formatted": "22.820562"' in text
    assert "balance_eth" not in text, "a token amount is not in ETH and must not say so"


async def test_get_balances_returns_the_native_row_and_the_token_row() -> None:
    """Test 16 (spec §S3). Both rows survive the handler, in order."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xabc",
            "balances": [_native_row("6700000000000000", "0.0067"), _usdc_row()],
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_balances", {}, rid=16), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"symbol": "ETH"' in text
    assert '"symbol": "USDC"' in text
    assert text.index('"symbol": "ETH"') < text.index('"symbol": "USDC"'), (
        "native first, then the registry — the order the core fixed"
    )
    # The native row keeps its alias; only it.
    assert text.count("balance_eth") == 1


def test_the_tool_schema_describes_what_a_row_carries() -> None:
    """Test 16, the schema half: the description names the new fields.

    A consumer that reads `balance` and divides by 10**18 is the failure this
    arc is about, and the tool description is where an agent looks first.
    """
    _protocol, registry = create_protocol_and_registry(None)
    tools = {tool.name: tool for tool in registry.list_tools()}

    balances = tools["get_balances"].description
    for field in ("balance_formatted", "decimals", "token_address"):
        assert field in balances, f"`{field}` must be described on get_balances"
    assert "only on a native-coin row" in balances

    context_desc = tools["get_wallet_context"].description
    assert "unavailable" in context_desc
    assert "balance_formatted" in context_desc


async def test_get_balances_explicit_address_adds_balance_eth() -> None:
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_balance = AsyncMock(return_value={"balance": "5000000000000000"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(
        _call(
            "get_balances",
            {"address": "0xA713e7145F0060A35E92a928e997B42481c0FfEE", "chain_id": 1},
            rid=3,
        ),
        context,
    )

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance": "5000000000000000"' in text
    assert '"balance_eth": "0.005"' in text
