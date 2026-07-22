# rustok-mcp

[![CI](https://github.com/rustok-org/mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rustok-org/mcp/actions/workflows/ci.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](https://github.com/rustok-org/mcp/blob/main/LICENSE)

> MCP Server for Rustok — connects Claude Desktop, Cursor, and cloud agents to the Rustok wallet via Gateway.

## Two editions

Rustok ships **two wallet products** — pick the trust model you want:

| | `rustok-wallet` (agent edition) | `rustok-wallet-tui` (this repo) |
|---|---|---|
| Who signs | the agent, unrestricted | **you**, in a separate terminal (`rustok-console`, y/N + PIN) |
| Where | [rustokwallet.com](https://rustokwallet.com) · [ClawHub](https://clawhub.ai/temrjan/skills/rustok-wallet) · image `ghcr.io/rustok-org/rustok-wallet` | this repo (`main`) · image `ghcr.io/rustok-org/rustok-wallet-tui` |
| Line | 0.4.x (maintained from the `wallet-v0.4.0` tag) | 0.5.x+ |

## Install (rustok-wallet-tui, self-custody)

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.8.2/scripts/install.sh | sh

rustok init             # creates the wallet — prints the 12 words + PIN once
rustok connect claude   # registers it with your agent (or: cursor / hermes)
```

The installer verifies the wallet image's cosign signature **before** anything
touches disk, pulls it by digest, and installs the `rustok` command — it never
touches a secret, a keystore or your wallet. Requires podman (or docker) and
cosign; you can read the script before running it. Full walkthrough, including
the by-hand setup without the shim: [Installation Guide](docs/INSTALL.md).

The wallet is one self-contained image (Core + Gateway + MCP over **stdio** + the
human-approval console); keys live only in a local container volume and never
leave your machine. Transactions that move funds are approved by a human in a
second terminal with `rustok console` — the agent cannot drive it.

## Install as an agent skill

The wallet skill ([`skills/rustok-wallet-tui/`](skills/rustok-wallet-tui/SKILL.md))
installs straight from this repo:

```bash
# skills CLI (Claude Code, Cursor, and other agents) — https://skills.sh
npx skills add rustok-org/mcp

# Hermes Agent
hermes skills tap add rustok-org/mcp
hermes skills install rustok-org/mcp/rustok-wallet-tui
```

The **agent edition** skill for OpenClaw is published on
[ClawHub](https://clawhub.ai/temrjan/skills/rustok-wallet); a ClawHub listing for
the TUI edition ships separately.

## Registries

- **Official MCP Registry** — the **agent edition** is published as
  [`io.github.rustok-org/rustok-wallet`](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.rustok-org/rustok-wallet)
  (OCI package `ghcr.io/rustok-org/rustok-wallet`, stdio). A TUI-edition
  registry entry ships separately as `io.github.rustok-org/rustok-wallet-tui`.
- **ClawHub** — the **agent edition** skill for OpenClaw:
  [clawhub.ai/temrjan/skills/rustok-wallet](https://clawhub.ai/temrjan/skills/rustok-wallet).

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
