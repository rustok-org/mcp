---
name: rustok-wallet
description: Self-custody Ethereum agent wallet. Runs entirely on the user's machine as one Docker image (MCP over stdio); private keys never leave it. Read wallet context, balances and DeFi positions (Aave v3, ERC-4626); preview, execute and sign. The user assumes all risk for funds on the agent wallet — there are no hard-coded spending limits.
version: 0.3.0
metadata:
  openclaw:
    emoji: "🦀"
    requires:
      bins:
        - docker
    homepage: https://github.com/rustok-org/mcp
---

# rustok-wallet

> **License note:** this OpenClaw skill package (`skills/rustok-wallet/`) is MIT-0
> per ClawHub requirements. The Rustok wallet core itself is proprietary; only the
> compiled binary image is distributed.

You are connected to a **self-custody** Ethereum agent wallet that runs entirely
on the user's machine as a single Docker image (`ghcr.io/rustok-org/rustok-wallet`).
The container runs the wallet core + gateway and speaks MCP over **stdio**; the
private keys live only in the user's local Docker volume and never leave it.

> ⚠️ **Self-custody, real funds, your risk.** This wallet has **no hard-coded
> spending limits or budgets** — the user consciously accepts that funds sent to
> the agent wallet are at risk. txguard still flags risky transactions, but it
> does not block them. All supported chains the user enables are live (incl.
> Ethereum mainnet). Always preview before executing and show the user the details.

## Prerequisites

- **Docker** installed and running.
- An Ethereum RPC URL (an Alchemy key URL is best; a public RPC works for testing).

## One-time onboarding (the user does this in a terminal, once)

Create the wallet and **back up the 24-word recovery phrase** — it is shown only
once, in the user's own terminal (never to the agent):

```bash
docker run -it --rm \
  -v rustok-wallet:/data \
  -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \
  ghcr.io/rustok-org/rustok-wallet:latest create-wallet
```

This prints the wallet **address** and the **24 words**. Write the words down
offline and fund the address. Recovery = these 24 words (importable into any
standard wallet, e.g. MetaMask) or the `rustok-wallet` Docker volume + password.

## How the agent runs the wallet

The MCP client launches the image over stdio (keys stay local):

```bash
docker run -i --rm --init \
  -v rustok-wallet:/data \
  -e RUSTOK_KEYRING_PASSWORD="..." \
  -e RUSTOK_ALLOWED_CHAINS="1,8453" \
  -e RUSTOK_RPC_URLS_1="https://your-rpc" \
  ghcr.io/rustok-org/rustok-wallet:latest
```

For **Claude Desktop / Cursor** (stdio MCP), add to the MCP config:

```json
{
  "mcpServers": {
    "rustok-wallet": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init",
               "-v", "rustok-wallet:/data",
               "-e", "RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet:latest"],
      "env": {
        "RUSTOK_KEYRING_PASSWORD": "...",
        "RUSTOK_RPC_URLS_1": "https://your-rpc"
      }
    }
  }
}
```

## Tools

The stdio wallet image is process-trusted and exposes **all** tools by default.
To run a restricted agent, set `RUSTOK_MCP_CAPABILITIES` to a subset
(`read_wallet` / `preview_tx` / `execute_tx`) — e.g. `read_wallet` for read-only.

| Tool | Capability | What it does |
|------|-----------|--------------|
| `get_wallet_context` | read_wallet | Active wallet address, per-chain balances, allowed chains |
| `get_balances` | read_wallet | Token balances for the active wallet, or `{address, chain_id}` |
| `get_positions` | read_wallet | DeFi positions — Aave v3 (collateral/debt/health factor/LTV) + ERC-4626 vaults; optional `{address}` |
| `preview_send` | preview_tx | Preview an ETH send `{to, amount, chain_id}` → `preview_id`, gas, risk level |
| `execute_send` | execute_tx | Broadcast a previewed send `{preview_id}` → `tx_hash` |
| `sign_message` | execute_tx | Sign a message (EIP-191) |

## Behavioral guidelines

1. **Always `preview_send` before `execute_send`** — never execute without a fresh preview.
2. **Show the preview** (amount, destination, estimated cost, risk level) before executing.
3. **Use `get_wallet_context` first** so you don't hallucinate balances or chains.
4. If a tool needs a capability the session lacks, it returns an authorization
   error — explain that to the user rather than retrying.
5. If the wallet is unreachable, tell the user the wallet container/onboarding may
   not be set up (see onboarding above).
