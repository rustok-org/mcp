"""JSON-RPC 2.0 protocol layer for MCP."""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel

JsonRpcHandler = Callable[["JsonRpcRequest", dict[str, Any] | None], Awaitable[Any]]


class JsonRpcError(BaseModel):
    """JSON-RPC error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC request object."""

    jsonrpc: Literal["2.0"]
    method: str
    id: int | str | None = None
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC response object."""

    jsonrpc: Literal["2.0"]
    id: int | str | None = None
    result: Any | None = None
    error: JsonRpcError | None = None


# JSON-RPC 2.0 standard errors
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# Application-defined server errors (-32000..-32099)
ERR_UNAUTHORIZED = -32002
ERR_CAPABILITY_REQUIRED = -32001
ERR_TX_BLOCKED = -32010
ERR_PRECONDITION = -32011
ERR_NOT_SUPPORTED = -32012
ERR_CORE_UNAVAILABLE = -32013
ERR_NOT_FOUND = -32014


class McpError(ValueError):
    """Custom error carrying a JSON-RPC error code."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(message)


class McpProtocol:
    """Routes JSON-RPC requests to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, JsonRpcHandler] = {}

    def register(self, method: str, handler: JsonRpcHandler) -> None:
        """Register a handler for a JSON-RPC method."""
        self._handlers[method] = handler

    async def handle(
        self,
        request: JsonRpcRequest,
        context: dict[str, Any] | None = None,
    ) -> JsonRpcResponse | None:
        """Process a JSON-RPC request and return a response.

        Returns ``None`` for notifications (no response required).
        """
        # Notifications have no id and do not expect a response
        if request.id is None:
            handler = self._handlers.get(request.method)
            if handler is not None:
                await handler(request, context)
            return None

        handler = self._handlers.get(request.method)
        if handler is None:
            return JsonRpcResponse(
                jsonrpc="2.0",
                id=request.id,
                error=JsonRpcError(
                    code=-32601,
                    message=f"Method not found: {request.method}",
                ),
            )

        try:
            result = await handler(request, context)
            return JsonRpcResponse(jsonrpc="2.0", id=request.id, result=result)
        except ValueError as exc:
            code = getattr(exc, "code", -32602)
            return JsonRpcResponse(
                jsonrpc="2.0",
                id=request.id,
                error=JsonRpcError(code=code, message=str(exc)),
            )
        except Exception as exc:  # noqa: BLE001
            return JsonRpcResponse(
                jsonrpc="2.0",
                id=request.id,
                error=JsonRpcError(code=-32603, message=str(exc)),
            )
