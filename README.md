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
docker run -p 127.0.0.1:3000:3000 rustok-mcp
```

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
