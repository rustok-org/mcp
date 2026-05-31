"""Stdio transport entrypoint for MCP (JSON-RPC over stdin/stdout)."""

import asyncio
import json
import sys
from typing import Any

from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcError, JsonRpcRequest, JsonRpcResponse


async def _stdio_loop() -> None:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
    protocol, _registry = create_protocol_and_registry()
    context: dict[str, Any] = {}

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
            request = JsonRpcRequest.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            response = JsonRpcResponse(
                jsonrpc="2.0",
                id=None,
                error=JsonRpcError(code=-32700, message=f"Parse error: {exc}"),
            )
            print(response.model_dump_json(), flush=True)
            continue

        result = await protocol.handle(request, context)
        if result is not None:
            print(result.model_dump_json(), flush=True)


def main() -> None:
    """Run the stdio MCP transport."""
    asyncio.run(_stdio_loop())
