"""Stdio transport entrypoint for MCP (placeholder)."""

import sys
import time


def main() -> None:
    """Placeholder stdio entrypoint for Claude Desktop integration.

    Full JSON-RPC over stdio will be implemented in PR-3.2.
    The process blocks so Claude Desktop does not see a crash loop.
    """
    print("rustok-mcp stdio transport placeholder", file=sys.stderr)
    # placeholder: real implementation will block on stdin
    while True:
        time.sleep(1)
