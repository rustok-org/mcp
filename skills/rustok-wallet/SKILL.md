---
name: rustok-wallet
description: Self-custody Ethereum Agent Wallet. All supported chains enabled by default (Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia). User assumes all risks. Runs locally. Preview/execute ETH sends with hard policy limits, track DeFi positions. All actions are append-only audit logged.
version: 0.2.1
metadata:
  openclaw:
    emoji: "🦀"
    requires:
      bins:
        - curl
        - jq
    homepage: https://github.com/rustok-org/mcp
---

# rustok-wallet

> **License note:** This OpenClaw skill package (`skills/rustok-wallet/`) is published under MIT-0 per ClawHub platform requirements. The Rustok project itself (`crates/`, `app/`, `mobile/`) remains under AGPL-3.0-or-later.

You are connected to an isolated Ethereum Agent Wallet via the local `rustok-agent-mcp` service (`http://127.0.0.1:3000`).

This wallet is **separate** from the user's main wallet. All spending limits, address blocklists, and daily budgets are enforced in **code** — you cannot negotiate them away. The wallet runs entirely on the user's machine; no private keys ever leave localhost.

> ⚠️ **Beta.** By default the wallet is configured for **all supported chains** including Ethereum mainnet (chain_id 1), Arbitrum One, Base, Optimism, zkSync Era, Sepolia, and Arbitrum Sepolia. **The user assumes all risks.** If you do not want mainnet access, restrict `allowed_chain_ids` via `--policy-config`.

## When to use

- User asks about wallet balance, address, or holdings
- User wants to send ETH or check transaction status
- User asks about DeFi positions (Aave, vaults)
- User asks to preview a transaction before executing

## Installation

### Option A — Download from GitHub Releases (recommended)

One-line install (Linux, macOS, Windows with Git Bash):

```bash
curl -fsSL https://raw.githubusercontent.com/temrjan/rustok/main/scripts/install-agent-mcp.sh | bash
```

Or download manually from [GitHub Releases](https://github.com/rustok-org/mcp/releases).

### Option B — Docker

For server deployment or headless operation:

```bash
docker run -p 127.0.0.1:3000:3000 \
  -v ~/.rustok/agent:/data \
  -e RUSTOK_AGENT_PASSWORD="your-password" \
  ghcr.io/rustok-org/rustok-mcp:latest
```

### Option C — Build from source

Requires Rust toolchain:

```bash
git clone https://github.com/rustok-org/mcp.git
cd rustok
cargo build --release --bin rustok-agent-mcp
```

## Desktop Installation (Claude Desktop / Cursor)

For native MCP integration via stdio (no HTTP server needed):

**1. Install the binary** (see Option A above).

**2. Configure Claude Desktop:**

Add to your Claude Desktop config:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

**3. Restart Claude Desktop.** The wallet tools will appear automatically.

> **Note:** In stdio mode the wallet auto-creates on first run if missing, uses unlimited policy defaults, and disables rate limiting. You control your own funds.

## Quick Start

### 1. Check wallet context

```bash
curl -fsS -X POST http://127.0.0.1:3000/context | jq
```

### 2. Preview a transaction (always preview before execute)

```bash
curl -fsS -X POST http://127.0.0.1:3000/preview \
  -H "Content-Type: application/json" \
  -d '{"to":"0x0000000000000000000000000000000000000001","amount_wei":"100000000000000000","chain_id":421614}' | jq
```

### 3. Execute a transaction (requires preview_id from step 2)

```bash
curl -fsS -X POST http://127.0.0.1:3000/execute \
  -H "Content-Type: application/json" \
  -d '{"to":"0x0000000000000000000000000000000000000001","amount_wei":"100000000000000000","chain_id":421614,"preview_id":"PASTE_PREVIEW_ID_HERE"}' | jq
```

## API Reference

### POST /context — Wallet state

Returns: address, cross-chain balances, policy limits, gas estimates.

```bash
curl -fsS -X POST http://127.0.0.1:3000/context | jq
```

### POST /positions — DeFi positions

Get Aave v3 + ERC-4626 positions for an address. Omit `address` to use the agent wallet's own address.

```bash
curl -fsS -X POST http://127.0.0.1:3000/positions \
  -H "Content-Type: application/json" \
  -d '{"address":"0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"}' | jq
```

### POST /preview — Simulate + risk analysis

Runs policy + budget checks and txguard risk analysis. Returns a `preview_id` that must be passed to `/execute`.

**Body:** `PreviewRequest`
```json
{
  "to": "0x0000000000000000000000000000000000000001",
  "amount_wei": "100000000000000000",
  "chain_id": 421614
}
```

```bash
curl -fsS -X POST http://127.0.0.1:3000/preview \
  -H "Content-Type: application/json" \
  -d '{"to":"0x0000000000000000000000000000000000000001","amount_wei":"100000000000000000","chain_id":421614}' | jq
```

**Response:** `PreviewResponse`
```json
{
  "preview_id": "550e8400-e29b-41d4-a716-446655440000",
  "verdict": {
    "action": "allow",
    "risk_score": 15,
    "findings": [],
    "description": "Send 0.1 ETH to 0x0000...0001",
    "simulation": {
      "eth_change": -100000000000000000,
      "token_changes": [],
      "approval_changes": [],
      "gas_used": 21000,
      "reverted": false
    }
  },
  "route": {
    "chain_id": 421614,
    "chain_name": "Ethereum",
    "estimated_gas": 21000,
    "max_fee_per_gas": "25000000000",
    "max_priority_fee_per_gas": "1500000000",
    "estimated_cost": "525000000000000",
    "available_balance": "1000000000000000000"
  },
  "explanation": "Send 0.1 ETH on Ethereum. Estimated cost: 0.000525 ETH (21k gas @ 25 gwei)."
}
```

### POST /execute — Sign and broadcast

Requires a valid `preview_id` from the preceding `/preview` call. Re-runs policy and budget checks as defense-in-depth.

**Body:** `ExecuteRequest`
```json
{
  "to": "0x0000000000000000000000000000000000000001",
  "amount_wei": "100000000000000000",
  "chain_id": 421614,
  "preview_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

```bash
curl -fsS -X POST http://127.0.0.1:3000/execute \
  -H "Content-Type: application/json" \
  -d '{"to":"0x0000000000000000000000000000000000000001","amount_wei":"100000000000000000","chain_id":421614,"preview_id":"PASTE_PREVIEW_ID_HERE"}' | jq
```

**Response on success:** `SendResult`
```json
{
  "tx_hash": "0xabc123...",
  "chain_id": 421614,
  "chain_name": "Ethereum",
  "from": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
  "to": "0x0000000000000000000000000000000000000001",
  "amount_wei": "100000000000000000",
  "estimated_gas_cost": "525000000000000"
}
```

**Response on policy block (HTTP 403):**
```
policy blocked: exceeds max_single_tx_eth
```

**Response on budget exceeded (HTTP 403):**
```
daily budget exceeded: 0.450000 / 0.500000 ETH
```

**Response on preview expired (HTTP 400):**
```
preview expired
```

**Response on preview mismatch (HTTP 400):**
```
preview mismatch
```

## Safety Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Spending limits | `AgentPolicy` — code-level checks before every tx |
| Daily budget | Rolling 24h accumulator in SQLite |
| Address blocklist | Exact match |
| Unlimited approvals blocked | `block_unlimited_approvals = true` rejects `type(uint256).max` |
| Audit immutability | Append-only `agent_audit_log` table |
| Wallet isolation | Separate `~/.rustok/agent/` directory |
| No prompt injection bypass | Limits are not in system prompt; they are in code |
| Local-only keys | Private keys never leave the user's machine |

## Behavioral Guidelines
1. **Always preview before execute.** Never call `/execute` without a fresh `/preview`.
2. **Respect policy blocks.** If the API returns 403, explain why to the user — do not retry.
3. **Show the preview to the user.** Before executing, summarize the preview (amount, destination, estimated cost, risk score).
4. **Use `/context` first.** Before any operation, check wallet state so you do not hallucinate balances or chain availability.
5. **Handle errors gracefully.** If `rustok-agent-mcp` is unreachable, inform the user that the wallet service is offline.

## Changelog

### 0.2.0
- Pivot to local-only self-custody model. No SaaS, no shared wallet.
- Removed API key requirement; auth is optional via `MCP_API_KEY` env var.
- Added dual-mode transport: HTTP server (`--transport http`) and stdio (`--transport stdio`) for Claude Desktop / Cursor.
- Added GitHub Releases with prebuilt binaries for Linux, macOS (Apple Silicon), and Windows.
- Added one-command install script.
- **All supported chains enabled by default** (Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia). Use `--policy-config` to restrict.

### 0.1.0
- Initial release
- Wallet context, ETH send (preview + execute)
- Aave v3 + ERC-4626 position tracking
- Hard policy gates and audit logging
- **Verified on-chain:** First agent-executed ETH transfer via Telegram (Sepolia, 2026-05-21) — tx hash `0x495e…13653`

---

## Supported Chains & Testnet ETH

By default the wallet is active on **all supported chains**:
- Ethereum mainnet (`1`)
- Arbitrum One (`42161`)
- Base (`8453`)
- Optimism (`10`)
- zkSync Era (`324`)
- Sepolia testnet (`11155111`)
- Arbitrum Sepolia testnet (`421614`)

To restrict chains, provide a custom policy file (`--policy-config policy.json`) with only the desired `allowed_chain_ids`.

### Testnet ETH (Arbitrum Sepolia)

For testing on **Arbitrum Sepolia** (`chain_id: 421614`) you need test ETH to pay gas.

**Faucets (free test ETH):**
- [Alchemy Arbitrum Sepolia Faucet](https://www.alchemy.com/faucets/arbitrum-sepolia) — 0.1 ETH/day (requires Alchemy account)
- [QuickNode Arbitrum Sepolia Faucet](https://faucet.quicknode.com/arbitrum/sepolia) — 0.1 ETH/day (requires QuickNode account)
- [Chainstack Faucet](https://faucet.chainstack.com) — variable amount (requires Chainstack account)

Most faucets require a small mainnet ETH balance (~0.001–0.5 ETH) as anti-bot protection. This balance is not spent.

## Support Development

If this skill helps you, consider sending ETH to support development:

**Ethereum:** `0xb9d2497e5356d75d0ddd6d806cfe13cafe65f6eb`

Every transaction helps improve agent wallet security. ☕
