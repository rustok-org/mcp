# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`rustok connect cursor` / `rustok connect hermes`** — the remaining two
  clients get the one-command registration. Cursor: a jq write into
  `~/.cursor/mcp.json` (no registrar CLI exists; atomic tmp+mv, the old
  entry printed back as the return path). Hermes: a python3+PyYAML
  round-trip into `~/.hermes/config.yaml` (`mcp_servers.rustok` with
  `enabled: true` and a REAL args list; backup + atomic write) that also
  replaces the Stage-0-era `rustok-wallet` entry (the args-as-JSON-string
  bug) and hints at removing the obsolete wrapper script. The wallet
  defaults to the client's own (`--agent` overrides) — every agent gets
  its own keystore.
- **`rustok connect claude`** — one-command MCP registration: builds the
  `claude mcp add -s user rustok` invocation (both labels, per-agent volume,
  keyring secret, RPC secrets, frozen `-e` config, image), with named
  refusals for every broken precondition (no init, env-file-era volume →
  migration path, already registered without `--force`, broken agent
  config JSON, missing jq) and a volume-domain warning when containers
  already share the keystore.
- **Per-chain RPC secrets** — `connect` stores every `RUSTOK_RPC_URLS_<chain>`
  as a podman secret `rustok-rpc-<agent>-<chain>` (atomic
  `secret create --replace`; `secret rm` is banned — it succeeds silently
  even on a held secret) and both the registration and `rustok start`
  deliver the URL through the secret, closing the documented
  inspect-visibility interim. Docker fallback keeps the honest literal
  `-e` (documented second tier).

### Changed
- Registration existence is probed by reading `$HOME/.claude.json` (jq,
  read-only; user-scope only) — never `claude mcp get`/`list`, which
  health-check and thereby start a wallet container on the shared keystore.

## [0.7.1] — 2026-07-15

### Fixed
- **MCP protocol version negotiation** — `initialize` now mirrors a supported
  client revision (2024-11-05 … 2025-11-25) instead of a hard-pinned
  2024-11-05, which current Claude Code silently rejects (30 s timeout, no
  wallet). Found by the first real user on day one.
- **JSON-RPC responses carry `result` XOR `error`** — every response used to
  ship `"error": null` next to its result (and vice versa), which a strict
  client parser (Claude Code 2.1) rejects as malformed; one serialization
  seam (`JsonRpcResponse.to_wire`) now emits exactly one of the two keys on
  both transports (stdio, SSE). This was the second, decisive half of the
  same connect failure.
- **serverInfo/OpenAPI/__version__ read the package metadata** — three
  hardcoded version strings could drift from the shipped version (the v0.7.0
  image reported 0.6.0).

## [0.7.0] — 2026-07-15

### Changed
- **Wallet image ships the resident console** (`rustok-console:v0.2.0`) on the
  first proto-2 core (`rustok-core:v0.3.0`): PIN-unlock opens a dashboard
  (balances, DeFi positions, "waiting for you"), decisions raise notices on a
  LIVING console instead of ending the process, Receive shows the address with
  a QR, Activity keeps a decision journal that outlives the core's retention
  window. Machine callers read one JSON line per decision from a non-TTY
  stdout; exit codes now report only how the session ended.
- **The e2e acceptance asserts the resident model**: outcome notices + the
  agent-side status (two layers of the same truth), the console surviving every
  decision, and `q` -> exit 6 as the only everyday way out. The v0.1
  per-decision exit codes (0/4, failed=1) and the "Pending approvals" screen
  no longer exist and are gone from the suite.

### Added
- **End-to-end acceptance suite** (`tests/e2e`, marker `e2e`): drives the shipped
  `rustok-wallet-tui` image through the real approval channel — the agent proposes over
  MCP stdio, a human decides in a pty-driven console, the core signs and broadcasts to a
  local anvil. Covers approve/deny/expiry/PIN-lockout/unlimited-approve/no-tty/no-auth.
  Not part of the default run (it needs podman): `uv run pytest -m e2e`.

### Documentation
- **Upgrading the wallet image** (INSTALL, TROUBLESHOOTING): the wallet lives in the
  volume, not the image; the pending approval queue does not survive a restart.

## [0.6.0] — 2026-07-11

### Added
- **`execute_transaction` tool** (capability `execute_tx`): parks a previewed
  transaction for human approval — the wallet never sends it on its own. A
  `pending` result carries a `next_step` hint pointing the human at the approval
  console (`docker exec -it rustok-wallet-tui rustok-console`).
- **`get_execution_status` tool** (capability `execute_tx`): polls a parked
  execution — `pending` / `executed` (+`tx_hash`) / `denied` / `expired` /
  `failed` (+`error_reason`), with the `not_after_unix` approval deadline.
- Gateway 404 `not_found` (unknown or expired `preview_id`) now reaches the
  agent as machine-readable `ERR_NOT_FOUND` (-32014) instead of a masked
  internal error, so status polling knows when to stop.
- `Dockerfile.wallet` carries `org.opencontainers.image.source` so GHCR links
  the package to this repository.

### Changed
- Version unified to **0.6.0** across manifests, docs, and image tags.

## [0.5.0] — 2026-07-10

### Renamed
- **The console-gated wallet is now its own product: `rustok-wallet-tui`**
  (image `ghcr.io/rustok-org/rustok-wallet-tui`, skill `skills/rustok-wallet-tui/`,
  container/volume `rustok-wallet-tui`). Renamed before announcement — the 0.5.0
  release had no consumers under the old name. `rustok-wallet` remains the
  unrestricted agent edition (0.4.x line: site, ClawHub, MCP Registry, `latest`).

### Added
- Wallet image now ships the human-approval console (`rustok-console:v0.1.0`) as
  `/usr/local/bin/rustok-console`.
- Onboarding prints both the 12-word recovery phrase and the 6-digit approval PIN.
- Two-window rule documented: human approvals happen in `docker exec -it
  rustok-wallet-tui rustok-console`, never inside the agent chat.

### Changed
- Wallet image version unified to **0.5.0** (`pyproject.toml`, `server.json`,
  `claw.json`, `SKILL.md`, `smithery.yaml`, docs).
- Core base image updated to `rustok-core:v0.2.0` (first core release with the
  approver socket + PIN + core-executes-on-approve).
- All `docker run` examples use the fixed container name `--name rustok-wallet-tui`
  (singleton) and explicit `v0.5.0` tag instead of `latest`.
- Mnemonic references across docs updated from 24 words to 12 words (org
  standard).
- `Dockerfile.wallet` pre-creates `/run/wallet` and `entrypoint.sh` recreates it
  on startup for podman tmpfs compatibility.

## [Unreleased]

> **Package reset:** the MCP server was rewritten from the v1 Rust binary
> `rustok-agent-mcp` (AGPL, ≤ 0.2.2) to a Python package **`rustok-mcp`** and the
> version line was reset to **0.1.0** (see `pyproject.toml`). The `[0.2.2]`,
> `[0.2.1]` and `[0.1.0]` entries below are **superseded v1 (Rust) history**, kept
> for the record.

### Added
- Distribution repository scaffold: install scripts, Docker, docs
- `get_wallet_context` and `get_balances` tools wired to Gateway REST
  (`GET /api/v1/wallet/context`) — stubs removed (PR-3.5)
- Optional `chain_id` filter argument for `get_balances`
- `RUSTOK_MCP_HOST` setting (default `127.0.0.1`; set `0.0.0.0` in Docker)

### Changed
- Server/image version unified to **0.3.2** (was 0.1.0) to match the ClawHub
  skill — `pyproject`, the FastAPI app, and the MCP `serverInfo` clients see at
  `initialize` now all report 0.3.2. Added `server.json` for the official MCP
  registry (OCI/stdio package) plus the required
  `io.modelcontextprotocol.server.name` image label in `Dockerfile.wallet`.
- Dockerfile rewritten for the Python server (uv multi-stage build,
  non-root runtime, SSE entrypoint); legacy Rust-binary image removed
- `get_balances` accepts optional `address` (+ required `chain_id`) and then
  queries `GET /api/v1/wallet/balance` instead of the wallet context
- 4xx Gateway errors: only the `message` field of the known error shape is
  forwarded; unrecognized bodies (e.g. dev stack traces) are logged and masked
- `.dockerignore` updated for the Python layout (`.venv`, `__pycache__`,
  caches, tests); legacy Rust patterns dropped
- `get_positions` tool (Aave v3 + ERC-4626) gated by `read_wallet`, backed by
  Gateway `GET /api/v1/wallet/positions`
- **Self-custody all-in-one image** `ghcr.io/rustok-org/rustok-wallet`
  (`Dockerfile.wallet`): runs Core + Gateway + MCP in one container and speaks
  MCP over **stdio** — keys stay in the user's local volume. One-time onboarding
  via `… create-wallet` (prints the 24-word recovery phrase once). Published by
  `.github/workflows/wallet-publish.yml` on version tags.
- The `rustok-wallet` skill (`skills/rustok-wallet/`) + `smithery.yaml` rewritten
  for the stdio Docker command (works on ClawHub, Smithery, Claude Desktop).

> **Migration (v1 → v2):** the wallet is now a Docker image run over stdio, not a
> single native binary. Existing v1 ClawHub installs keep working until you
> migrate: pull `rustok-wallet`, run `create-wallet`, and update your MCP config
> to the new `docker run -i` command (see `docs/INSTALL.md`).

### Removed
- v1 Rust-binary distribution: the fake-binary `release.yml` workflow, the
  dummy-`rustok-agent-mcp` build step in `docker-publish.yml`, and the dropped
  hard-policy example (`skills/rustok-wallet/examples/policy.json`). The MCP is a
  Python package/image now; the spend-limit/budget policy model is intentionally
  not part of the wallet (risk is the user's to accept).
- `cargo`-based checklist in the PR template (replaced with ruff/mypy/pytest).

## [0.2.2] — 2026-05-27

### Changed
- Migrated from `temrjan/rustok` to `rustok-org/mcp`
- Updated all installation URLs to new organization

## [0.2.1] — 2026-05-24

### Added
- Dual-mode transport: HTTP server and stdio for Claude Desktop / Cursor
- GitHub Releases with prebuilt binaries (Linux, macOS Apple Silicon, Windows)
- One-command install script
- Docker image published to GHCR

### Changed
- All supported chains enabled by default (Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia)
- Removed API key requirement; auth optional via `MCP_API_KEY`

## [0.1.0] — 2026-05-21

### Added
- Initial release of rustok-agent-mcp
- Wallet context, ETH send (preview + execute)
- Aave v3 + ERC-4626 position tracking
- Hard policy gates and audit logging
- Verified on-chain: first agent-executed ETH transfer via Telegram (Sepolia)
