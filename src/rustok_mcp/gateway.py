"""Gateway HTTP client for Rustok REST API."""

import logging
from typing import Any

import httpx

from rustok_mcp.protocol import McpError

logger = logging.getLogger(__name__)


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

    async def wallet_context(self) -> Any:
        return await self._get("/api/v1/wallet/context")

    async def get_balance(self, address: str, chain_id: int) -> Any:
        return await self._get(
            "/api/v1/wallet/balance",
            params={"address": address, "chain_id": chain_id},
        )

    async def preview_send(self, to: str, amount: str, chain_id: int) -> Any:
        return await self._post(
            "/api/v1/wallet/preview_send",
            {"to": to, "amount": amount, "chain_id": chain_id},
        )

    async def execute_send(self, preview_id: str) -> Any:
        return await self._post(
            "/api/v1/wallet/execute_send",
            {"preview_id": preview_id},
        )

    async def sign_message(self, message: str, sign_type: str) -> Any:
        return await self._post(
            "/api/v1/wallet/sign_message",
            {"message": message, "sign_type": sign_type},
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        """Send a POST request, mapping transport failures to McpError.

        Connection refusal / timeout is raised at request time (here), not by
        ``raise_for_status``, so it must be caught around the request itself.
        """
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise McpError(-32603, "Gateway timeout") from exc
        except httpx.ConnectError as exc:
            raise McpError(-32603, "Gateway unreachable") from exc
        except httpx.RequestError as exc:
            # Any other transport-level error (read/write/protocol) — do not
            # leak the raw httpx exception to the client.
            logger.warning("gateway request error for %s: %s", path, exc)
            raise McpError(-32603, "Gateway request failed") from exc
        return self._handle_response(response)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request, mapping transport failures to McpError."""
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise McpError(-32603, "Gateway timeout") from exc
        except httpx.ConnectError as exc:
            raise McpError(-32603, "Gateway unreachable") from exc
        except httpx.RequestError as exc:
            logger.warning("gateway request error for %s: %s", path, exc)
            raise McpError(-32603, "Gateway request failed") from exc
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise McpError(-32002, "Unauthorized") from exc
            if status >= 500:
                # 5xx bodies may carry internal details — log, do not forward.
                logger.warning("gateway %s response: %s", status, exc.response.text)
                raise McpError(-32603, "Gateway internal error") from exc
            # 4xx: forward only the `message` field of the known Gateway error
            # shape ({"error": ..., "message": ...}) — validation messages are
            # actionable for the caller. Anything else (e.g. a stack trace from
            # a misconfigured dev Gateway) is logged and masked.
            message = self._known_error_message(exc.response)
            if message is not None:
                raise ValueError(f"Gateway request failed: {message}") from exc
            logger.warning(
                "gateway %s response with unrecognized body: %s",
                status,
                exc.response.text,
            )
            raise ValueError("Gateway request failed") from exc
        return response.json()

    @staticmethod
    def _known_error_message(response: httpx.Response) -> str | None:
        """Return the `message` field if the body matches the Gateway error shape."""
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, str):
                return message
        return None
