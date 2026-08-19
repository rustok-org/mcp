# Configuration

All configuration is via environment variables passed to the wallet container.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RUSTOK_KEYRING_PASSWORD` | Yes² | — | Unlocks your local keystore (set at `create-wallet`). **Never commit it.** The compatibility delivery: prefer `RUSTOK_KEYRING_PASSWORD_FILE` below. Passed this way the value lands in the container config (`inspect`) — the entrypoint stages it in a `0600` file, clears it from every process and deletes the file once the core has unlocked, but the config copy is outside the image's reach. In an `--env-file`, quotes also become part of the password. |
| `RUSTOK_KEYRING_PASSWORD_FILE` | Yes² | — | Path to a file *inside the container* holding the keystore password (podman secret `type=mount`, or a bind-mounted `0600` file). Used only when `RUSTOK_KEYRING_PASSWORD` is not set; trailing newlines are stripped; a missing/non-regular/empty file fails with a named error. |
| `RUSTOK_ALLOWED_CHAINS` | No | `1,8453,42161` | Comma-separated chain IDs to enable — Ethereum, Base and Arbitrum unless you say otherwise (e.g. `1,8453,42161,10`). |
| `RUSTOK_RPC_URLS_<chain>` | No¹ | two public nodes per chain | RPC URL(s) for a chain, e.g. `RUSTOK_RPC_URLS_1=https://…`. Comma-separated for fallbacks. **What you name replaces what the build carries — it is not added to it** — and an empty value means "read nothing on this chain" rather than "use theirs". |
| `RUSTOK_ALCHEMY_API_KEY` | No¹ | — | Alchemy key (primary RPC for supported chains). |
| `RUSTOK_VAULTS_<chain>` | No | — | Comma-separated ERC-4626 vault addresses to track on a chain (opt-in). |
| `RUSTOK_TOKENS_<chain>` | No | — | ERC-20 tokens to show the balance of on a chain, `SYMBOL:ADDRESS:DECIMALS`, comma-separated — e.g. `RUSTOK_TOKENS_42161=USDC:0xaf88d065e77c8cC2239327C5EDb3A432268e5831:6`. Explicit, and opt-in for anything beyond USDC: a chain you register nothing for shows the USDC the build carries, and a chain you do register replaces that list rather than adding to it. Beyond those, the wallet shows what you registered and does not go looking. A malformed entry, a duplicate address on one chain, or a chain absent from `RUSTOK_ALLOWED_CHAINS` **fails startup** with a message naming the chain — a token registry that is quietly half-loaded is worse than one that refuses. The same symbol at two addresses is fine (native USDC and bridged USDC.e both exist). **`SYMBOL` and `DECIMALS` are taken from you, not read from the contract** — both are optional in ERC-20 and a contract is free to call itself `USDC` with 18 places, so the operator's word is what decides how the number reaches the screen. Get `DECIMALS` wrong and the wallet will show a wrong amount confidently: check it against the contract before you register it. |

> **What `connect --force` keeps, and what it rebuilds.** A re-run rebuilds the
> registration from the environment of **that shell**, so a `RUSTOK_*` you set
> once and did not export again is not carried over — it is simply absent from
> the new entry. The exception is engine-specific: on **podman** an RPC URL
> survives, because it lives in the per-agent secret store rather than in the
> entry; on **docker** there is no store, so it is a literal like everything
> else and is rebuilt too. `--force` names what it is about to drop before it
> writes — read that line.

| `RUSTOK_DATA_DIR` | No | `/data` | Keystore directory inside the container (mount a volume here). |
| `RUSTOK_MCP_CAPABILITIES` | No | all | Restrict the stdio agent to a comma-separated capability subset (`read_wallet`,`preview_tx`,`execute_tx`). Unset → all (stdio is process-trusted). |

¹ Since 0.11.0 neither is required for the chains the build carries endpoints for
(1, 8453, 42161, 10, 11155111): those read without configuration. A key makes the
wallet reach that provider first and the public list second; a chain outside that
set still needs one of the two, or it is skipped (no balances/positions for it).
Whichever you end up reading through, the node **learns the address and the IP**
that asked about it — the carried ones, yours, and your provider's alike.

² Exactly one of the two: the password itself, **or** the path to a file holding it
(the explicit password wins if both are set).

## Data & keys

- Mount a named volume at `/data`: `-v rustok-wallet-tui:/data`. It holds the
  encrypted `keystore.json` and the approval-PIN hash. **Your backup is the
  12-word phrase**, not the volume: a copy of the volume opens only with the
  keyring password, which through the shim is generated and lives outside the
  volume. Losing the phrase and the volume+password together loses the wallet.
- Keys are encrypted at rest (Argon2id + AES-256-GCM) and only ever decrypted
  inside the container on your machine.

## Approval console

The wallet core listens for human approvals on a UNIX socket at
`/run/wallet/approve.sock` inside the container. The directory is created by the
image — it is not a volume and not a user setting. To review and approve or deny
a pending transaction, open the console in a separate terminal:

```bash
rustok console
```

Without the shim: the container runs under an auto-generated name (labels, not
`--name`), so find it by label.

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" rustok-console
```

## Capabilities (security)

Each tool is gated by a capability:

| Capability | Tools |
|------------|-------|
| `read_wallet` | `get_wallet_context`, `get_balances`, `get_positions` |
| `preview_tx` | `preview_transaction` |
| `execute_tx` | `execute_transaction`, `get_execution_status` |

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
