"""MCP tool registry and decorators."""

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class Tool(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class ToolRegistry:
    """Registry of available tools with their handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool: Tool, handler: ToolHandler) -> None:
        """Register a tool and its handler."""
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    def list_tools(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool definitions as JSON-compatible dicts."""
        return [tool.model_dump() for tool in self._tools.values()]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with the given arguments."""
        if name not in self._handlers:
            raise ValueError(f"Tool not found: {name}")
        return await self._handlers[name](arguments)
