"""Tool registry tests."""

import pytest

from rustok_mcp.tools import Tool, ToolRegistry


async def _ping_handler(_args: dict[str, str]) -> str:
    return "pong"


async def _echo_handler(args: dict[str, str]) -> str | None:
    return args.get("message")


async def _none_handler(_args: dict[str, str]) -> None:
    return None


async def test_register_and_list_tools() -> None:
    """Registered tools appear in list_tools."""
    registry = ToolRegistry()
    registry.register(
        Tool(name="ping", description="Ping", inputSchema={"type": "object"}),
        _ping_handler,
    )

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "ping"


async def test_call_tool() -> None:
    """call() executes the registered handler."""
    registry = ToolRegistry()
    registry.register(
        Tool(name="echo", description="Echo", inputSchema={"type": "object"}),
        _echo_handler,
    )

    result = await registry.call("echo", {"message": "hello"})
    assert result == "hello"


async def test_call_unknown_tool_raises() -> None:
    """Calling an unregistered tool raises ValueError."""
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Tool not found: missing"):
        await registry.call("missing", {})


async def test_get_tool_schemas() -> None:
    """get_tool_schemas returns JSON-compatible dicts."""
    registry = ToolRegistry()
    registry.register(
        Tool(name="a", description="A", inputSchema={"type": "object"}),
        _none_handler,
    )

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "a"
