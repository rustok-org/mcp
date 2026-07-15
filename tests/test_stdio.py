"""Stdio transport tests."""

import io
import json
from unittest.mock import patch

import pytest

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
    assert response["result"]["protocolVersion"] == "2025-11-25"


async def test_stdio_default_exposes_all_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """A standard MCP client (caps object, no rustok list) sees all 7 tools over stdio."""
    monkeypatch.delenv("RUSTOK_MCP_CAPABILITIES", raising=False)
    requests = (
        json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    )
    stdin = io.StringIO(requests)
    stdout = io.StringIO()

    with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
        await _stdio_loop()

    stdout.seek(0)
    lines = [line for line in stdout.read().splitlines() if line.strip()]
    tools_response = json.loads(lines[1])
    names = {tool["name"] for tool in tools_response["result"]["tools"]}
    assert names == {
        "get_wallet_context",
        "get_balances",
        "get_positions",
        "preview_transaction",
        "sign_message",
        "execute_transaction",
        "get_execution_status",
    }


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
