"""Gateway HTTP client tests."""

import json

import httpx
import pytest

from rustok_mcp.gateway import DEFAULT_GATEWAY_TIMEOUT_SECONDS, GatewayClient
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import (
    ERR_CORE_UNAVAILABLE,
    ERR_INTERNAL,
    ERR_INVALID_PARAMS,
    ERR_NOT_SUPPORTED,
    ERR_PRECONDITION,
    ERR_TX_BLOCKED,
    ERR_UNAUTHORIZED,
    McpError,
)


async def test_preview_transaction_success() -> None:
    """preview_transaction returns the Gateway response on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wallet/preview_transaction"
        body = json.loads(request.content)
        assert body == {"to": "0x123", "data": "", "value": "1.0", "chain_id": 1}
        return httpx.Response(200, json={"preview_id": "abc", "estimated_gas": "21000"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.preview_transaction("0x123", "1.0", 1)
    assert result == {"preview_id": "abc", "estimated_gas": "21000"}
    await client.close()


async def test_sign_message_success() -> None:
    """sign_message returns signature on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wallet/sign_message"
        return httpx.Response(200, json={"signature": "0xsig"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.sign_message("hello", "eip191")
    assert result == {"signature": "0xsig"}
    await client.close()


async def test_wallet_context_success() -> None:
    """wallet_context returns Gateway response on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/wallet/context"
        return httpx.Response(
            200,
            json={
                "address": "0xabc",
                "balances": [{"chain_id": 1, "symbol": "ETH", "balance": "100"}],
                "allowed_chains": [1],
            },
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.wallet_context()
    assert result["address"] == "0xabc"
    assert result["balances"][0]["chain_id"] == 1
    await client.close()


async def test_get_balance_success() -> None:
    """get_balance passes query params and returns balance on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/wallet/balance"
        assert request.url.params["address"] == "0xabc"
        assert request.url.params["chain_id"] == "1"
        return httpx.Response(200, json={"balance": "42"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.get_balance("0xabc", 1)
    assert result == {"balance": "42"}
    await client.close()


async def test_get_positions_success() -> None:
    """get_positions forwards the address param and returns positions on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/wallet/positions"
        assert request.url.params["address"] == "0xabc"
        return httpx.Response(200, json={"positions": [{"protocol": "aave_v3"}]})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.get_positions("0xabc")
    assert result["positions"][0]["protocol"] == "aave_v3"
    await client.close()


async def test_get_positions_no_address_omits_param() -> None:
    """get_positions without an address sends no query params (active wallet)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wallet/positions"
        assert "address" not in request.url.params
        return httpx.Response(200, json={"positions": []})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.get_positions()
    assert result == {"positions": []}
    await client.close()


async def test_wallet_context_connect_error_raises_mcperror() -> None:
    """GET transport failures map to McpError like POST ones."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.wallet_context()
    assert exc_info.value.code == -32603
    await client.close()


async def test_4xx_bad_request_maps_to_invalid_params() -> None:
    """400 bad_request maps to ERR_INVALID_PARAMS and forwards the message."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "bad_request", "message": "unsupported chain id: 99"},
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 99)
    assert exc_info.value.code == ERR_INVALID_PARAMS
    assert "unsupported chain id: 99" in str(exc_info.value)
    await client.close()


async def test_4xx_unrecognized_body_is_masked() -> None:
    """4xx with an unrecognized body (e.g. a stack trace) is masked as internal."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Traceback (most recent call last): secret")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == ERR_INTERNAL
    assert "secret" not in str(exc_info.value)
    assert "Traceback" not in str(exc_info.value)
    await client.close()


async def test_409_tx_blocked_maps_to_actionable_error() -> None:
    """409 tx_blocked reaches the agent as ERR_TX_BLOCKED with the reason."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": "tx_blocked",
                "message": "known scam recipient 0xdeadbeef",
            },
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == ERR_TX_BLOCKED
    assert "known scam recipient 0xdeadbeef" in str(exc_info.value)
    assert "Transaction blocked by policy" in str(exc_info.value)
    await client.close()


async def test_409_precondition_failed_maps_to_actionable_error() -> None:
    """409 precondition_failed reaches the agent as ERR_PRECONDITION."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"error": "precondition_failed", "message": "wallet is locked"},
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == ERR_PRECONDITION
    assert "wallet is locked" in str(exc_info.value)
    await client.close()


async def test_501_not_supported_maps_to_actionable_error() -> None:
    """501 not_supported reaches the agent as ERR_NOT_SUPPORTED."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            501,
            json={"error": "not_supported", "message": "EIP-712 signing is not supported"},
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.sign_message("hello", "eip712")
    assert exc_info.value.code == ERR_NOT_SUPPORTED
    assert "EIP-712 signing is not supported" in str(exc_info.value)
    await client.close()


async def test_503_core_unavailable_maps_to_actionable_error() -> None:
    """503 core_unavailable reaches the agent as ERR_CORE_UNAVAILABLE."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": "core_unavailable", "message": "core service unavailable"},
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.wallet_context()
    assert exc_info.value.code == ERR_CORE_UNAVAILABLE
    assert "Core unavailable" in str(exc_info.value)
    await client.close()


async def test_500_internal_error_is_masked() -> None:
    """500 internal_error is masked as ERR_INTERNAL; body detail is not forwarded."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "internal_error", "message": "secret stack trace detail"},
        )

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.sign_message("hello", "eip191")
    assert exc_info.value.code == ERR_INTERNAL
    assert "secret" not in str(exc_info.value)
    assert "Gateway internal error" in str(exc_info.value)
    await client.close()


async def test_unauthorized_raises_mcperror() -> None:
    """401/403 responses raise McpError with code -32002."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == ERR_UNAUTHORIZED
    assert "Unauthorized" in str(exc_info.value)
    await client.close()


async def test_5xx_unrecognized_body_is_masked() -> None:
    """5xx responses with unrecognized bodies raise McpError(ERR_INTERNAL)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.sign_message("hello", "eip191")
    assert exc_info.value.code == ERR_INTERNAL
    await client.close()


async def test_auth_header_set_when_api_key_provided() -> None:
    """Authorization header is sent when api_key is provided."""
    received_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received_headers.update(dict(request.headers))
        return httpx.Response(200, json={"preview_id": "abc"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", api_key="secret", transport=transport)
    await client.preview_transaction("0x123", "1.0", 1)
    assert received_headers.get("authorization") == "Bearer secret"
    await client.close()


async def test_auth_header_not_set_without_api_key() -> None:
    """No Authorization header when api_key is None."""
    received_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received_headers.update(dict(request.headers))
        return httpx.Response(200, json={"preview_id": "abc"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", api_key=None, transport=transport)
    await client.preview_transaction("0x123", "1.0", 1)
    assert "authorization" not in {k.lower() for k in received_headers}
    await client.close()


async def test_connect_error_raises_gateway_unreachable() -> None:
    """A refused connection maps to McpError(-32603) 'Gateway unreachable'."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == -32603
    assert "unreachable" in str(exc_info.value).lower()
    await client.close()


async def test_timeout_raises_gateway_timeout() -> None:
    """A request timeout maps to McpError(-32603) 'Gateway timeout'."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == -32603
    assert "timeout" in str(exc_info.value).lower()
    await client.close()


async def test_generic_request_error_hits_fallback() -> None:
    """A non-timeout, non-connect transport error hits the RequestError fallback."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.WriteError("write failed", request=request)

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.preview_transaction("0x123", "1.0", 1)
    assert exc_info.value.code == -32603
    assert str(exc_info.value) == "Gateway request failed"
    await client.close()


async def test_5xx_body_not_leaked_to_client() -> None:
    """5xx response body is not forwarded in the error message."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Traceback: internal secret detail")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.sign_message("hello", "eip191")
    assert exc_info.value.code == ERR_INTERNAL
    assert "secret" not in str(exc_info.value)
    await client.close()


async def test_sign_message_description_contains_phishing_warning() -> None:
    """The sign_message tool description warns about arbitrary signatures."""
    _, registry = create_protocol_and_registry()
    schemas = {schema["name"]: schema for schema in registry.get_tool_schemas()}
    schema = schemas["sign_message"]
    assert "arbitrary bytes" in schema["description"]
    assert "DRAIN" in schema["description"]
    assert "EIP-712" in schema["description"]


def test_default_gateway_timeout() -> None:
    """The default outbound timeout is just past the gateway's 10s layer."""
    assert DEFAULT_GATEWAY_TIMEOUT_SECONDS == 11.0


async def test_gateway_timeout_is_configurable() -> None:
    """GatewayClient timeout is exposed and applied to the httpx client."""
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={}))
    client = GatewayClient("http://gateway", timeout=5.0, transport=transport)
    assert client._client.timeout.read == 5.0
    await client.close()
