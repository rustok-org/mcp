"""Unit tests for ETH↔wei amount conversion and unit-explicit responses."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from rustok_mcp.capabilities import Capability
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import _eth_to_wei, _wei_to_eth, create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcRequest


@pytest.mark.parametrize(
    ("amount_eth", "expected_wei"),
    [
        ("1", "1000000000000000000"),
        ("1.0", "1000000000000000000"),
        ("0.05", "50000000000000000"),
        ("0.000000000000000001", "1"),
        ("1.500000000000000000", "1500000000000000000"),
        ("123456789.987654321", "123456789987654321000000000"),
        # 27 integral digits + 18 decimals: far beyond supply, must stay exact.
        (
            "999999999999999999999999999.999999999999999999",
            "999999999999999999999999999999999999999999999",
        ),
    ],
)
def test_eth_to_wei_converts_exactly(amount_eth: str, expected_wei: str) -> None:
    assert _eth_to_wei(amount_eth) == expected_wei


@pytest.mark.parametrize(
    "amount_eth",
    [
        "0",
        "0.0",
        "0.000000000000000000",
        "1e5",
        "1E5",
        "NaN",
        "Infinity",
        "+1",
        "-1",
        " 1 ",
        "1.",
        ".5",
        "",
        "0x10",
        "1_000",
        "1,5",
        "1.0000000000000000001",  # 19 decimal places — below 1 wei
        "1234567890123456789012345678",  # 28 integral digits
        1.0,  # not a string
        None,
        {"amount": "1"},
    ],
)
def test_eth_to_wei_rejects_bad_input(amount_eth: Any) -> None:
    with pytest.raises(ValueError, match="amount_eth"):
        _eth_to_wei(amount_eth)


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


def _preview_request(arguments: dict[str, Any]) -> JsonRpcRequest:
    return JsonRpcRequest(
        jsonrpc="2.0",
        id=1,
        method="tools/call",
        params={"name": "preview_send", "arguments": arguments},
    )


async def test_preview_send_converts_eth_to_wei_for_gateway() -> None:
    """The gateway receives the exact wei integer, not the ETH string."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.preview_send = AsyncMock(return_value={"preview_id": "real-id"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(
        _preview_request({"to": "0xabc", "amount_eth": "0.05", "chain_id": 1}),
        context,
    )

    assert response is not None
    assert response.error is None
    mock_client.preview_send.assert_awaited_once_with(
        to="0xabc", amount="50000000000000000", chain_id=1
    )


async def test_preview_send_rejects_legacy_amount_field() -> None:
    """The old wei-interpreted `amount` must fail loudly, not silently re-scale."""
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(
        _preview_request({"to": "0xabc", "amount": "1", "chain_id": 1}),
        context,
    )

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    assert "amount_eth" in response.error.message
    mock_client.preview_send.assert_not_awaited()


async def test_preview_send_rejects_bad_amount_eth_before_gateway() -> None:
    mock_client = AsyncMock(spec=GatewayClient)
    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(
        _preview_request({"to": "0xabc", "amount_eth": "1e5", "chain_id": 1}),
        context,
    )

    assert response is not None
    assert response.error is not None
    assert response.error.code == -32602
    mock_client.preview_send.assert_not_awaited()


async def test_preview_response_carries_explicit_units() -> None:
    """The gateway's wei `amount` is replaced by amount_wei + amount_eth."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.preview_send = AsyncMock(
        return_value={
            "preview_id": "id-1",
            "amount": "1000000000000000000",
            "estimated_gas": 21000,
        }
    )

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    response = await protocol.handle(
        _preview_request({"to": "0xabc", "amount_eth": "1", "chain_id": 1}),
        context,
    )

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"amount_wei": "1000000000000000000"' in text
    assert '"amount_eth": "1"' in text
    assert '"amount"' not in text.replace('"amount_wei"', "").replace('"amount_eth"', "")


async def test_preview_send_stub_mode_still_validates() -> None:
    """Without a gateway client, bad/missing amount_eth must still be rejected."""
    protocol, _registry = create_protocol_and_registry()
    context = {"capabilities": set(Capability)}

    bad = await protocol.handle(
        _preview_request({"to": "0xabc", "amount_eth": "1e5", "chain_id": 1}), context
    )
    assert bad is not None
    assert bad.error is not None
    assert bad.error.code == -32602

    missing = await protocol.handle(_preview_request({"to": "0xabc", "chain_id": 1}), context)
    assert missing is not None
    assert missing.error is not None
    assert missing.error.code == -32602


async def test_get_balances_explicit_address_adds_balance_eth() -> None:
    """The explicit-address branch enriches its single entry with balance_eth."""
    mock_client = AsyncMock(spec=GatewayClient)
    mock_client.get_balance = AsyncMock(return_value={"balance": "5000000000000000"})

    protocol, _registry = create_protocol_and_registry(mock_client)
    context = {"capabilities": set(Capability)}
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=4,
        method="tools/call",
        params={
            "name": "get_balances",
            "arguments": {"address": "0xA713e7145F0060A35E92a928e997B42481c0FfEE", "chain_id": 1},
        },
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance": "5000000000000000"' in text
    assert '"balance_eth": "0.005"' in text


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
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=2,
        method="tools/call",
        params={"name": "get_balances", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance": "5000000000000000"' in text
    assert '"balance_eth": "0.005"' in text


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
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id=3,
        method="tools/call",
        params={"name": "get_wallet_context", "arguments": {}},
    )
    response = await protocol.handle(request, context)

    assert response is not None
    assert response.result is not None
    text = response.result["content"][0]["text"]
    assert '"balance_eth": "1"' in text
