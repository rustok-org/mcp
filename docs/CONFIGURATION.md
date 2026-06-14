# Configuration

All configuration is via environment variables passed to the wallet container.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RUSTOK_KEYRING_PASSWORD` | Yes | — | Unlocks your local keystore (set at `create-wallet`). **Never commit it.** |
| `RUSTOK_ALLOWED_CHAINS` | No | `1,8453` | Comma-separated chain IDs to enable (e.g. `1,8453,42161,10`). |
| `RUSTOK_RPC_URLS_<chain>` | No¹ | — | RPC URL(s) for a chain, e.g. `RUSTOK_RPC_URLS_1=https://…`. Comma-separated for fallbacks. |
| `RUSTOK_ALCHEMY_API_KEY` | No¹ | — | Alchemy key (primary RPC for supported chains). |
| `RUSTOK_VAULTS_<chain>` | No | — | Comma-separated ERC-4626 vault addresses to track on a chain (opt-in). |
| `RUSTOK_DATA_DIR` | No | `/data` | Keystore directory inside the container (mount a volume here). |

¹ Provide **either** an Alchemy key **or** a public RPC URL per enabled chain;
otherwise that chain is skipped (no balances/positions for it).

## Data & keys

- Mount a named volume at `/data`: `-v rustok-wallet:/data`. It holds the
  encrypted `keystore.json`. Back it up (or the 24-word phrase) — losing both
  loses the wallet.
- Keys are encrypted at rest (Argon2id + AES-256-GCM) and only ever decrypted
  inside the container on your machine.

## Capabilities (security)

Tools are gated by capabilities the MCP client grants on connect:

| Capability | Tools |
|------------|-------|
| `read_wallet` | `get_wallet_context`, `get_balances`, `get_positions` |
| `preview_tx` | `preview_send` |
| `execute_tx` | `execute_send`, `sign_message` |

## No spending policy

This wallet has **no hard-coded spending limits, budgets, or blocklists** — by
design (you consciously accept the risk of funds on the agent wallet). `txguard`
still analyses transactions and surfaces a risk level on preview, but it does not
block. Opt-in user-configurable limits may be added later.
