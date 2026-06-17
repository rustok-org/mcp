"""Gateway HTTP client for Rustok REST API."""

import logging
from typing import Any

import httpx

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

    async def get_positions(self, address: str | None = None) -> Any:
        # Empty/None address → the active wallet's own positions (Core resolves it).
        params = {"address": address} if address else None
        return await self._get("/api/v1/wallet/positions", params=params)

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
            raise self._error_from_response(exc.response) from exc
        return response.json()

    @staticmethod
    def _error_from_response(response: httpx.Response) -> McpError:
        """Map a non-2xx Gateway response to a structured MCP error.

        Routes on the machine-readable ``error`` field when the body matches the
        known Gateway shape; masks unrecognized 4xx/5xx bodies so internal
        details never reach the agent.
        """
        status = response.status_code
        if status in (401, 403):
            return McpError(ERR_UNAUTHORIZED, "Unauthorized")

        error_code, message = _parse_gateway_error(response)

        if error_code is not None:
            match error_code:
                case "tx_blocked":
                    return McpError(ERR_TX_BLOCKED, f"Transaction blocked by policy: {message}")
                case "precondition_failed":
                    return McpError(ERR_PRECONDITION, message)
                case "not_supported":
                    return McpError(ERR_NOT_SUPPORTED, message)
                case "bad_request":
                    return McpError(ERR_INVALID_PARAMS, message)
                case "core_unavailable":
                    return McpError(ERR_CORE_UNAVAILABLE, f"Core unavailable: {message}")
                case _:
                    # Known shape but unrecognized error code — still safer to mask.
                    logger.warning(
                        "gateway returned unrecognized error code %r (status %s): %s",
                        error_code,
                        status,
                        response.text,
                    )
                    return McpError(ERR_INTERNAL, "Gateway internal error")

        # No recognized error shape: 5xx bodies and unrecognized 4xx bodies may
        # carry internal details — log server-side, mask client-side.
        if status >= 500:
            logger.warning("gateway %s response: %s", status, response.text)
        else:
            logger.warning(
                "gateway %s response with unrecognized body: %s",
                status,
                response.text,
            )
        return McpError(ERR_INTERNAL, "Gateway internal error")


def _parse_gateway_error(response: httpx.Response) -> tuple[str | None, str]:
    """Extract (error_code, message) from a Gateway error body.

    Returns ``(None, "")`` when the body does not match the expected shape.
    """
    try:
        body = response.json()
    except ValueError:
        return None, ""
    if not isinstance(body, dict):
        return None, ""
    error_code = body.get("error")
    message = body.get("message", "")
    if isinstance(error_code, str) and isinstance(message, str):
        return error_code, message
    return None, ""
