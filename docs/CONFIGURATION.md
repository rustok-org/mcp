# Configuration

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RUSTOK_AGENT_PASSWORD` | Yes | — | Wallet unlock password. **Never commit this.** |
| `MCP_API_KEY` | No | — | Bearer token for HTTP API auth. Empty = disabled. |
| `MCP_CHAIN_IDS` | No | `421614` | Comma-separated allowed chain IDs. |
| `MCP_RATE_LIMIT` | No | `100` | Requests per minute limit. `0` = disabled. |

## Claude Desktop Config

Add to `claude_desktop_config.json`:

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

## Policy Configuration

Create `policy.json` for custom limits:

```json
{
  "max_single_tx_eth": 0.5,
  "max_daily_spend_eth": 2.0,
  "max_gas_fee_gwei": 100,
  "allowed_chain_ids": [1, 42161, 8453, 421614],
  "blocked_addresses": [],
  "block_unlimited_approvals": true
}
```

Run with policy:

```bash
rustok-agent-mcp --transport http --policy-config policy.json
```

## HTTP Server Options

```bash
rustok-agent-mcp --transport http --host 127.0.0.1 --port 3000
```

## Data Directory

Default: `~/.rustok/agent/`

Contains:
- `keystore/` — encrypted wallet files
- `audit.db` — SQLite append-only audit log

Override:

```bash
rustok-agent-mcp --data-dir /custom/path
```
