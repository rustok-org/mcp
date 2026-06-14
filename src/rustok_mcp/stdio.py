"""Stdio transport entrypoint for MCP (JSON-RPC over stdin/stdout)."""

import asyncio
import json
import sys
from typing import Any

from rustok_mcp.capabilities import resolve_stdio_capabilities
from rustok_mcp.config import get_settings
from rustok_mcp.gateway import GatewayClient
from rustok_mcp.handlers import create_protocol_and_registry
from rustok_mcp.protocol import JsonRpcError, JsonRpcRequest, JsonRpcResponse
from rustok_mcp.telemetry import init_telemetry


async def _stdio_loop() -> None:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
    settings = get_settings()
    gateway_client = GatewayClient(
        base_url=settings.gateway_url,
        api_key=settings.api_key,
    )
    try:
        protocol, _registry = create_protocol_and_registry(gateway_client)
        # stdio is process-trusted: seed the granted capabilities so a standard
        # MCP client (which cannot send the rustok capability list) still sees the
        # tools. `initialize` only narrows this if the client sends an explicit list.
        context: dict[str, Any] = {
            "capabilities": resolve_stdio_capabilities(settings.capabilities),
        }

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
    finally:
        await gateway_client.close()


def main() -> None:
    """Run the stdio MCP transport."""
    settings = get_settings()
    # JSON logs to stderr (stdout carries JSON-RPC) + httpx tracing when an OTLP
    # endpoint is set. No FastAPI server span in stdio mode.
    init_telemetry(settings.app_name, settings.log_level)
    asyncio.run(_stdio_loop())
