"""Stdio transport entrypoint for MCP (placeholder)."""

import sys


def main() -> None:
    """Placeholder stdio entrypoint for Claude Desktop integration.

    Full JSON-RPC over stdio will be implemented in PR-3.2.
    """
    print("rustok-mcp stdio transport placeholder", file=sys.stderr)
    sys.exit(0)
