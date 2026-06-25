# rustok-mcp

[![CI](https://github.com/rustok-org/mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rustok-org/mcp/actions/workflows/ci.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](https://github.com/rustok-org/mcp/blob/main/LICENSE)

> MCP Server for Rustok — connects Claude Desktop, Cursor, and cloud agents to the Rustok wallet via Gateway.

## Install (self-custody wallet)

The wallet ships as one self-contained Docker image (Core + Gateway + MCP over
**stdio**); keys live only in a local Docker volume and never leave your machine.
Follow the [Installation Guide](docs/INSTALL.md): run `create-wallet` once, then
add it as a stdio MCP server in Claude Desktop / Cursor.

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

> ⚠️ The MCP has **no built-in brute-force / rate-limit protection**. Terminate it
> behind the edge proxy (Caddy) with host-level rate limiting (see the
> [`rustok-org/meta`](https://github.com/rustok-org/meta) deploy docs); do not
> expose it to the internet directly.

## What is Rustok?

Rustok is a **self-custody AI-native crypto wallet**. The MCP Server is a thin
bridge between LLM agents and the Rustok Gateway — private keys never leave the
Core service (they stay in the local keystore volume).

- **Self-custody**: keys are encrypted at rest (Argon2id + AES-256-GCM) and only
  decrypted inside Core on your machine.
- **Capability-gated tools** (`read_wallet` / `preview_tx` / `execute_tx`): the
  stdio transport is process-trusted (all by default; restrict with
  `RUSTOK_MCP_CAPABILITIES`); the network-facing SSE transport is bearer-gated.
- **No spending policy by design**: no hard-coded limits, budgets, or blocklists —
  you consciously accept the risk of funds on the agent wallet. `txguard` surfaces
  a risk level on preview but does not block. Opt-in limits may come later.
- **Chains are opt-in**: set `RUSTOK_ALLOWED_CHAINS` (default `1,8453` — Ethereum +
  Base); enable another chain by providing its RPC (`RUSTOK_RPC_URLS_<id>` or an
  Alchemy key).
- **Informed preview**: `preview_transaction` returns the decoded call (who/what is
  authorized), a pre-sign simulation (revert check), gas, and a txguard risk level.
  Execution is not exposed as an MCP tool.
- **Audit logging**: every action is append-only logged to SQLite in Core.

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Changelog](CHANGELOG.md)
- [Security Policy](SECURITY.md)

## License

This repository is licensed under **MIT-0**.

The Rustok Core wallet engine is a proprietary artifact built from the private `rustok-org/core` repository.
