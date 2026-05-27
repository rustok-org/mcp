# Troubleshooting

## Installation

### "Unsupported OS" or "Unsupported architecture"

Check your platform:

```bash
uname -s   # OS
uname -m   # Architecture
```

Supported: Linux (x86_64, arm64), macOS (Intel, Apple Silicon), Windows x86_64.

If your platform is not supported, use Docker:

```bash
docker run -p 127.0.0.1:3000:3000 \
  -e RUSTOK_AGENT_PASSWORD="your-password" \
  ghcr.io/rustok-org/rustok-mcp:v0.2
```

### "Checksum mismatch"

The downloaded binary may be corrupted. Retry:

```bash
curl -fsSL https://raw.githubusercontent.com/rustok-org/mcp/main/scripts/install.sh | bash
```

If the error persists, check the [GitHub Releases](https://github.com/rustok-org/mcp/releases) page for known issues.

### "Failed to determine latest release"

GitHub API rate limit exceeded. Set a token:

```bash
export GITHUB_TOKEN="ghp_xxx"
curl -fsSL ... | bash
```

---

## Runtime

### "failed to unlock wallet"

- Ensure `RUSTOK_AGENT_PASSWORD` is set
- Check that the wallet exists (`~/.rustok/agent/keystore/`)
- Use `--create-wallet` to create a new one:
  ```bash
  rustok-agent-mcp --transport http --create-wallet
  ```

### "wallet locked" in stdio mode

In stdio mode the wallet auto-creates if missing. If you see this error, check:

```bash
ls ~/.rustok/agent/keystore/
```

If empty, restart Claude Desktop — the wallet will be recreated on next stdio connection.

### "chain X not allowed"

The target chain is not in `MCP_CHAIN_IDS`. Set it:

```bash
export MCP_CHAIN_IDS="1,42161,8453,421614"
```

Or use `--policy-config` with explicit `allowed_chain_ids`.

### "policy blocked" or "daily budget exceeded"

Policy limits are enforced in code — they cannot be bypassed. Check your policy:

```bash
curl -fsS -X POST http://127.0.0.1:3000/context | jq '.policy'
```

Adjust `policy.json` or wait for the daily budget window to reset (24h rolling).

---

## Docker

### "permission denied" on volume mount

Ensure the host directory is writable by uid 1000:

```bash
mkdir -p ~/.rustok/agent
chown -R 1000:1000 ~/.rustok/agent
```

### Container exits immediately

Check logs:

```bash
docker logs <container_id>
```

Common cause: missing `RUSTOK_AGENT_PASSWORD`.

---

## Claude Desktop / Cursor

### Tools not appearing

1. Restart Claude Desktop completely (quit, not just close window)
2. Check config path:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
3. Validate JSON syntax
4. Check Claude logs for MCP errors:
   ```bash
   tail -f ~/Library/Logs/Claude/mcp*.log
   ```

### "connection refused" or "transport error"

In stdio mode, ensure the binary is in your PATH:

```bash
which rustok-agent-mcp
```

If not found, add `~/.local/bin` to PATH or use absolute path in config.

---

## Getting help

- [GitHub Issues](https://github.com/rustok-org/mcp/issues)
- [Security issues](SECURITY.md)
