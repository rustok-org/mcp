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
| `RUSTOK_MCP_CAPABILITIES` | No | all | Restrict the stdio agent to a comma-separated capability subset (`read_wallet`,`preview_tx`,`execute_tx`). Unset → all (stdio is process-trusted). |

¹ Provide **either** an Alchemy key **or** a public RPC URL per enabled chain;
otherwise that chain is skipped (no balances/positions for it).

## Data & keys

- Mount a named volume at `/data`: `-v rustok-wallet:/data`. It holds the
  encrypted `keystore.json`. Back it up (or the 12-word phrase + approval PIN) —
  losing all three loses the wallet.
- Keys are encrypted at rest (Argon2id + AES-256-GCM) and only ever decrypted
  inside the container on your machine.

## Approval console

The wallet core listens for human approvals on a UNIX socket at
`/run/wallet/approve.sock` inside the container. The directory is created by the
image — it is not a volume and not a user setting. To review and approve or deny
a pending transaction, open the console in a separate terminal:

```bash
docker exec -it rustok-wallet rustok-console
```

## Capabilities (security)

Each tool is gated by a capability:

| Capability | Tools |
|------------|-------|
| `read_wallet` | `get_wallet_context`, `get_balances`, `get_positions` |
| `preview_tx` | `preview_transaction` |
| `execute_tx` | `sign_message` |

The **stdio** transport (the `docker run -i` wallet image) is process-trusted —
whoever launches it owns the machine — so it grants **all** capabilities by
default. To run a restricted (e.g. read-only) agent, set `RUSTOK_MCP_CAPABILITIES`
to a comma-separated subset, e.g. `RUSTOK_MCP_CAPABILITIES=read_wallet`. The
network-facing **SSE** transport ignores this and stays gated until a client
grants capabilities on connect.

## No spending policy

This wallet has **no hard-coded spending limits, budgets, or blocklists** — by
design (you consciously accept the risk of funds on the agent wallet). `txguard`
still analyses transactions and surfaces a risk level on preview, but it does not
block. Opt-in user-configurable limits may be added later.
