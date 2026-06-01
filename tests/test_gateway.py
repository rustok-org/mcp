"""Gateway HTTP client tests."""

import json

import httpx
import pytest

from rustok_mcp.gateway import GatewayClient
from rustok_mcp.protocol import McpError


async def test_preview_send_success() -> None:
    """preview_send returns Gateway response on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wallet/preview_send"
        body = json.loads(request.content)
        assert body == {"to": "0x123", "amount": "1.0", "chain_id": 1}
        return httpx.Response(200, json={"preview_id": "abc", "estimated_gas": "21000"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.preview_send("0x123", "1.0", 1)
    assert result == {"preview_id": "abc", "estimated_gas": "21000"}
    await client.close()


async def test_execute_send_success() -> None:
    """execute_send returns tx_hash on 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wallet/execute_send"
        return httpx.Response(200, json={"tx_hash": "0xdeadbeef"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    result = await client.execute_send("preview-123")
    assert result == {"tx_hash": "0xdeadbeef"}
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


async def test_preview_send_4xx_raises_valueerror() -> None:
    """4xx responses raise ValueError with Gateway message."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "Bad request"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(ValueError, match="Gateway request failed"):
        await client.preview_send("0x123", "1.0", 1)
    await client.close()


async def test_unauthorized_raises_mcperror() -> None:
    """401/403 responses raise McpError with code -32002."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.execute_send("preview-123")
    assert exc_info.value.code == -32002
    assert "Unauthorized" in str(exc_info.value)
    await client.close()


async def test_5xx_raises_mcperror() -> None:
    """5xx responses raise McpError with code -32603."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", transport=transport)
    with pytest.raises(McpError) as exc_info:
        await client.sign_message("hello", "eip191")
    assert exc_info.value.code == -32603
    await client.close()


async def test_auth_header_set_when_api_key_provided() -> None:
    """Authorization header is sent when api_key is provided."""
    received_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received_headers.update(dict(request.headers))
        return httpx.Response(200, json={"preview_id": "abc"})

    transport = httpx.MockTransport(handler)
    client = GatewayClient("http://gateway", api_key="secret", transport=transport)
    await client.preview_send("0x123", "1.0", 1)
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
    await client.preview_send("0x123", "1.0", 1)
    assert "authorization" not in {k.lower() for k in received_headers}
    await client.close()
