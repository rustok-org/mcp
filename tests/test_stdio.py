"""Stdio transport tests."""

import io
import json
from unittest.mock import patch

from rustok_mcp.stdio import _stdio_loop


async def test_stdio_initialize_roundtrip() -> None:
    """Stdio loop reads JSON-RPC request and writes response to stdout."""
    request_line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    stdin = io.StringIO(request_line + "\n")
    stdout = io.StringIO()

    with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
        await _stdio_loop()

    stdout.seek(0)
    lines = [line for line in stdout.read().splitlines() if line.strip()]
    assert len(lines) == 1

    response = json.loads(lines[0])
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2024-11-05"


async def test_stdio_parse_error() -> None:
    """Invalid JSON input produces a Parse Error response."""
    stdin = io.StringIO("not json\n")
    stdout = io.StringIO()

    with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
        await _stdio_loop()

    stdout.seek(0)
    lines = [line for line in stdout.read().splitlines() if line.strip()]
    assert len(lines) == 1

    response = json.loads(lines[0])
    assert response["error"]["code"] == -32700
