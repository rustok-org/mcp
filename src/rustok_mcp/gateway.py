"""Gateway HTTP client for Rustok REST API."""

from typing import Any

import httpx

from rustok_mcp.protocol import McpError


class GatewayClient:
    """Async HTTP client for the Rustok Gateway."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=self._auth_headers(api_key),
            timeout=30.0,
            transport=transport,
        )

    def _auth_headers(self, api_key: str | None) -> dict[str, str]:
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return {}

    async def close(self) -> None:
        await self._client.aclose()

    async def preview_send(self, to: str, amount: str, chain_id: int) -> Any:
        response = await self._client.post(
            "/api/v1/wallet/preview_send",
            json={"to": to, "amount": amount, "chain_id": chain_id},
        )
        return self._handle_response(response)

    async def execute_send(self, preview_id: str) -> Any:
        response = await self._client.post(
            "/api/v1/wallet/execute_send",
            json={"preview_id": preview_id},
        )
        return self._handle_response(response)

    async def sign_message(self, message: str, sign_type: str) -> Any:
        response = await self._client.post(
            "/api/v1/wallet/sign_message",
            json={"message": message, "sign_type": sign_type},
        )
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise McpError(-32002, "Unauthorized") from exc
            if exc.response.status_code >= 500:
                raise McpError(-32603, f"Gateway error: {exc.response.text}") from exc
            raise ValueError(f"Gateway request failed: {exc.response.text}") from exc
        except httpx.ConnectError as exc:
            raise McpError(-32603, "Gateway unreachable") from exc
        except httpx.TimeoutException as exc:
            raise McpError(-32603, "Gateway timeout") from exc
        return response.json()
