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


async def test_wallet_context_adds_balance_eth() -> None:
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.wallet_context = AsyncMock(
        return_value={
            "address": "0xabc",
            "allowed_chains": [1],
            "balances": [{"chain_id": 1, "symbol": "ETH", "balance": "1000000000000000000"}],
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
            "balances": [{"chain_id": 1, "symbol": "ETH", "balance": "5000000000000000"}],
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(_call("get_balances", {}, rid=2), context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance_eth": "0.005"' in text


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
