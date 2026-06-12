# rustok-mcp

[![CI](https://github.com/rustok-org/mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rustok-org/mcp/actions/workflows/ci.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](https://github.com/rustok-org/mcp/blob/main/LICENSE)

> MCP Server for Rustok — connects Claude Desktop, Cursor, and cloud agents to the Rustok wallet via Gateway.

## Quick Start (Development)

```bash
# Install dependencies
uv sync --dev

# Run the server
uv run rustok-mcp

# Or run stdio transport
uv run rustok-mcp-stdio
```

## Docker

```bash
docker build -t rustok-mcp .
docker run -p 127.0.0.1:3001:3001 -e RUSTOK_MCP_HOST=0.0.0.0 rustok-mcp
```

To run the full stack (MCP → Gateway → Core + Redis), use the compose file
in [`rustok-org/meta`](https://github.com/rustok-org/meta).

> ⚠️ `scripts/install.sh` still targets the legacy Rust binary release;
> it will be adapted in a follow-up PR.

## Authentication

The network-facing SSE transport is gated by a shared bearer token.

- **Inbound** (`RUSTOK_MCP_INBOUND_API_KEY`) — clients must send
  `Authorization: Bearer <token>` to reach `/mcp/sse` and `/mcp/message`.
  Distinct from the **outbound** `RUSTOK_MCP_API_KEY` (MCP → Gateway).
- **Dev:** leave it empty — the loopback flow stays open and the server logs a
  warning at startup.
- **Prod:** required. The token must travel in the request header, **never in a
  query string** (query strings leak into access logs). Generate one with
  `openssl rand -hex 32`.
- The browser `EventSource` API cannot set headers and is **not** a supported
  client; use an MCP client that sends request headers.
- `/health` is always public (used by the container healthcheck).
- The local **stdio** transport is process-trusted and not gated.

> ⚠️ A publicly exposed MCP has **no brute-force / rate-limit protection** until
> PR-5.2 (observability + rate limiting). Do not expose it to the internet
> before then, even with a high-entropy token.

## What is Rustok?

Rustok is a **self-custody AI-native crypto wallet**. The MCP Server runs as a bridge between LLM agents and the Rustok Gateway — private keys never leave the Core service.

- **All supported chains enabled by default**: Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia
- **Policy enforcement**: Spending limits, daily budgets, blocklists — enforced in Core, not prompts
- **Audit logging**: Every action is append-only logged to SQLite in Core
- **Preview before execute**: Always simulate before signing

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Changelog](CHANGELOG.md)
- [Security Policy](SECURITY.md)

## License

This repository is licensed under **MIT-0**.

The Rustok Core wallet engine is a proprietary artifact built from the private `rustok-org/core` repository.
