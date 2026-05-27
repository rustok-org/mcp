#!/usr/bin/env bash
# Health check script for rustok-agent-mcp.
# Returns 0 if server is healthy, 1 otherwise.

set -euo pipefail

PORT="${RUSTOK_AGENT_PORT:-3000}"
HEALTH_URL="http://127.0.0.1:${PORT}/health"

echo "Checking rustok-agent-mcp health at ${HEALTH_URL}..."

if response=$(curl -fsS "${HEALTH_URL}" 2>/dev/null); then
    if [ "$response" = "ok" ]; then
        echo "✅ MCP server is healthy (port ${PORT})"
        exit 0
    else
        echo "⚠️ Unexpected response: $response"
        exit 1
    fi
else
    echo "❌ MCP server is not responding on port ${PORT}"
    echo ""
    echo "To start the server:"
    echo "  export RUSTOK_AGENT_PASSWORD=\"your_password\""
    echo "  ./target/release/rustok-agent-mcp --create-wallet --policy-config ~/.rustok/policy.json"
    echo ""
    exit 1
fi
