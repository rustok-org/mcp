# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-07-05

Skill-package docs patch (image unchanged, stays 0.4.0).

### Fixed
- ClawHub static analysis flagged the onboarding example's placeholder password
  (`RUSTOK_KEYRING_PASSWORD="choose-a-strong-password"`) as an exposed secret
  literal. The example now reads the password via `read -r -s` and passes the
  env var by name (`-e RUSTOK_KEYRING_PASSWORD`) — nothing secret-shaped in the
  file, and the password no longer lands in shell history or `ps`.

## [0.4.0] - 2026-07-05

Maintenance release of the all-in-one wallet image + skill, fixing the defects
found by the 2026-07-05 deep smoke test. Image base: core `v0.1.2`
(= `v0.1.1` + `SignTypedData` gRPC/route + honest preview errors + sign guard).

### Changed
- **BREAKING — `preview_send` amount contract.** The old `amount` field was
  documented as "Amount in ETH" but interpreted by core as a **wei integer**
  (fractional amounts were impossible; `"1"` meant 1 wei). The field is renamed
  to **`amount_eth`** (plain decimal string, max 18 decimal places) and is
  converted to an exact wei integer in the MCP layer. Requests still using
  `amount` fail loudly with a rename hint — never silently re-scaled.
- `preview_send` responses now carry explicit units: `amount_wei` + `amount_eth`
  (the ambiguous `amount` is gone).
- `get_wallet_context` / `get_balances` responses: `balance` stays wei and an
  explicit `balance_eth` is added alongside.
- Insufficient balance during preview now surfaces as a clear precondition
  error (was: misleading `Core unavailable`) — core `v0.1.2` fix.

### Added
- The wallet image now exposes `POST /api/v1/wallet/sign_typed_data`
  (EIP-712 over a pre-computed `domain_separator`/`struct_hash`) on the
  loopback gateway — unblocks glue-layer integrations (UniswapX order signing).

### Security
- `sign_message` is now guarded **server-side** (core `v0.1.2`): empty,
  oversized (>4 KiB), non-UTF-8, control-character and raw-hex-blob payloads
  are rejected before the signer is touched. Previously only the tool
  description asked agents to refuse hex blobs.

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
