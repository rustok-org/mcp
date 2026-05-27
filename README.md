# rustok-mcp

[![CI](https://github.com/rustok-org/mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rustok-org/mcp/actions/workflows/ci.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](https://github.com/rustok-org/mcp/blob/main/LICENSE)
[![GHCR](https://img.shields.io/badge/GHCR-latest-orange)](https://github.com/rustok-org/mcp/pkgs/container/rustok-mcp)

> **Distribution repository** for the Rustok MCP agent. This repo contains installation scripts, Docker images, and documentation. The agent binary is built from the private core repository and published here as a release artifact.

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/rustok-org/mcp/main/scripts/install.sh | bash
```

Supports **Linux (x86_64, arm64)**, **macOS (Apple Silicon, Intel)**, and **Windows (x86_64)**.

## Docker

```bash
docker run -p 127.0.0.1:3000:3000 \
  -v ~/.rustok/agent:/data \
  -e RUSTOK_AGENT_PASSWORD="your-strong-password" \
  ghcr.io/rustok-org/rustok-mcp:v0.2
```

## Claude Desktop / Cursor

Add to your MCP server config:

```json
{
  "mcpServers": {
    "rustok-wallet": {
      "command": "rustok-agent-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "RUSTOK_AGENT_PASSWORD": "your-strong-password"
      }
    }
  }
}
```

## What is Rustok?

Rustok is a **self-custody AI-native crypto wallet**. The MCP agent runs entirely on your local machine — private keys never leave localhost.

- **All supported chains enabled by default**: Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia
- **Policy enforcement**: Spending limits, daily budgets, blocklists — enforced in code, not prompts
- **Audit logging**: Every action is append-only logged to SQLite
- **Preview before execute**: Always simulate before signing

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Changelog](CHANGELOG.md)
- [Security Policy](SECURITY.md)

## License

This repository (scripts, docs, Dockerfiles) is licensed under **MIT-0**.

The Rustok agent binary is a proprietary artifact built from the private core repository. See [LICENSE](LICENSE) for details.
