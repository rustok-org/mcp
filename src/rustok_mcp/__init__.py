"""Rustok MCP Server — FastAPI with SSE and stdio transports."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rustok-mcp")
except PackageNotFoundError:  # a raw source tree, not an installed package
    __version__ = "0.0.0+unknown"
