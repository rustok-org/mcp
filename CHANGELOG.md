# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **The keyring password no longer lives in any process's environment.**
  Until now every process in the wallet image — core, the gateway and the MCP
  server — carried it in `/proc/<pid>/environ`, where anything running as the
  same user could read it, decrypt `keystore.json` directly and re-mint the
  approval PIN. Reading `/proc/*/environ` is the cheapest secret harvest there
  is, and it made the console edition's PIN gate bypassable. Only the core ever
  needed the password; the other two held it because the entrypoint exported it.

  Now the password reaches the core as a *file*, and only as a file. Supplied
  the documented way (a mounted secret plus `RUSTOK_KEYRING_PASSWORD_FILE`), it
  is in no environment at all and `podman inspect` carries a path instead of the
  value. Supplied the compatibility way (`-e RUSTOK_KEYRING_PASSWORD`), the
  entrypoint stages it in a 0600 file, drops the variable, and removes the file
  once the core has unlocked — and because the entrypoint is now PID 1 and hands
  that role to `tini` through `exec`, even PID 1's own environment is rewritten.
  A file *you* mounted is never deleted.

  **What this does not cover, stated plainly:** with `-e` delivery the value
  still sits in the container config (`podman inspect`) and, under `--init`, in
  the runtime's own PID 1 — neither is reachable from inside the image, which is
  why the file delivery is the documented one. Nothing here defends against code
  already running as the same user: it can read the staged file during its short
  life, the core's memory, and the data volume. Measured on podman 5.8.4; docker
  is not installed on the machine these runs were made on, so its behaviour is
  expected to match by mechanism but is **not verified**.

- **`rustok init`/`start`/`connect` now deliver the password as a mounted
  secret**, not `--secret …,type=env`. The generated command was the leaky path
  itself: documentation alone would have fixed the advice and not the product.
  Existing registrations keep working; re-run `rustok connect <client>` to move
  an already-registered client onto the new command.

- **Secret files on disk are owner-only** (core `v0.3.1`). `keystore.json` and
  `approval-pin.json` were world-readable (0644) — they are now written 0600 and
  narrowed on the first start of an existing wallet, which says so in the log.

### Changed
- **`--init` is gone from every documented command.** The entrypoint is PID 1
  itself and hands the role to `tini` through `exec`, so signal forwarding and
  zombie reaping are covered without it; with `-e` delivery an extra init
  process is a carrier nothing inside the image can clear.
- The image is built on core `v0.3.1` (from `v0.3.0`).

### Added
- **`rustok connect openclaw`.** OpenClaw was unsupported, so the first
  third-party agent to install this wallet had to route around us: generate the
  command with `rustok connect claude`, then register it in OpenClaw by hand.
  The client is now first-class across the whole lifecycle — `connect`, `update`,
  `uninstall` and `doctor` — not just in the dispatcher, so `rustok update` no
  longer walks past a registration it cannot see.

  Registration goes through OpenClaw's own CLI (`openclaw mcp set`), which
  **replaces** an entry in a single call: unlike the `claude` path there is no
  remove→add window in which the wallet is registered nowhere. `openclaw mcp
  reload` follows the write, so a session already open stops serving the cached
  command instead of failing on the next turn; a failed reload warns rather than
  failing the registration that has already landed.

  One thing worth knowing before you uninstall: OpenClaw refuses a config write
  made through its own CLI when the file shrinks too far — its message carries
  the token `size-drop`, and `openclaw config unset` hits the same guard.
  `rustok uninstall` relays OpenClaw's own words and the recovery that was
  measured end to end: `openclaw doctor --fix` (it writes the defaults back and
  raises the size the guard compares against), then repeat `openclaw mcp unset
  rustok`. Editing the config outside OpenClaw is not gated and also works; it
  only earns a one-line `Config observe anomaly` notice afterwards.

### Removed
- **The donation ask is gone from everything an agent reads.** The server's
  `initialize` instructions and the published skill both asked the model to
  raise the subject of supporting this project — with an address and suggested
  amounts — with the human it works for. An agent meeting the wallet for the
  first time flagged it unprompted, as something baked into the tool rather than
  what its human had asked for. A product trusted with keys does not lobby the
  agent on its author's behalf. The ask lives on the website, where a human
  chooses to read it.

### Fixed
- **A skipped signature check now says so where it gets read.** When `cosign` is
  unavailable the installer has always announced the skip — in the middle of a
  long install log, where it scrolls away. The first third party to install this
  wallet did not notice, and worked out from the outside that provenance had
  never been checked. The closing summary now repeats it and names the version
  requirement where it is actionable: the check needs **cosign 3 or newer**,
  because our signatures are OCI referrers that 2.x cannot see at all. Nothing
  about the install changes — the image is still pulled by digest, and a
  signature that is present but does not verify still stops everything.
- **The console command the wallet prints now works.** `initialize`, the
  `next_step` of every parked transaction and the `execute_transaction`
  description all told the human to run
  `docker exec -it rustok-wallet-tui rustok-console`. There is no container by
  that name — the wallet is launched by label, on purpose — so the command
  failed for anyone who installed the documented way, and it named `docker` on a
  product that recommends `podman`. All three now name `rustok console` first
  and the label-discovery form second, with the engine left to the reader. The
  grep-invariant that has guarded this exact papercut since July covered only
  the docs; it covers the source and its tests now, which is why it stayed green
  while the defect shipped.
- **A client can no longer expand its own capabilities via `initialize`.**
  The rustok capability list now *intersects* with the transport-seeded
  ceiling instead of replacing it: an operator launching the wallet with
  `RUSTOK_MCP_CAPABILITIES=read_wallet` gets a session the agent cannot talk
  out of (audit B1). With no seeded ceiling the granted set fails closed to
  empty — the server seeds, the client only narrows. The same env ceiling
  now also seeds SSE sessions (they keep the gated-until-granted contract
  only when it is unset).
- **The capability ceiling now also follows the wallet core's policy mode.**
  `initialize` reads `policy_mode` from the core (via WalletContext, core
  increment 1): `read_only` leaves read + preview tools, `supervised` /
  `autonomous` keep the full set while the core itself parks or denies
  writes. When the core is unreachable the transport ceiling applies alone,
  with a warning — MCP-side filtering is advisory; enforcement lives in the
  core.
- **A second `initialize` on the same SSE session can no longer change its
  capabilities.** The guard was the falsy empty set, so a standard MCP
  capabilities *object* (which parses to empty) left the session open to a
  second, wider grant. The session now tracks `initialized` explicitly.

### Changed
- **`sign_message` schema matches its documented contract.** The `sign_type`
  enum listed `eip712` while the tool description said EIP-712 is not
  supported; the enum is now `["eip191"]`.

## [0.8.1] — 2026-07-22

### Fixed
- **cosign is no longer a hard prerequisite of the one-command install.** The
  first live install hit a wall the release had not anticipated: `install.sh`
  refused to run without `cosign`, which Fedora does not carry in its
  repositories — so "one command" became "first go and find a verification tool
  somewhere". Integrity never depended on it: the image is pulled **by digest**
  (content-addressed — those bytes or nothing) and the script itself ships from
  an immutable tag. cosign proves *provenance* (built by this repo's workflow),
  which is a layer worth having and a poor gate. The installer now branches
  three ways, and never silently: cosign missing **or unable to run** → warns,
  names the digest, prints the command to check provenance later, and continues;
  cosign works and the signature verifies → says so and continues; cosign works
  and the signature does **not** verify → still refuses, fail-closed.
- **A broken cosign is no longer reported as a tampered image.** Branching on
  `command -v` answered "is there a file called cosign", not "can it run" — and
  answered it differently per shell (for a present-but-non-executable file
  `/bin/sh` says no, `bash` says yes). A cosign that exists but cannot execute
  (no `+x`, wrong architecture, missing libc, truncated download) therefore
  reached `cosign verify`, whose non-zero exit is indistinguishable from a bad
  signature, and the user was told their image was tampered with. The installer
  now probes with `cosign version` first and treats "cannot run" as "no cosign".
- **The refusal message stopped over-claiming.** Keyless verification reaches the
  Sigstore transparency log over the network, so a failed check may equally mean
  no connectivity, a rate limit or an outdated cosign. The message now names both
  possibilities instead of announcing sabotage; the behaviour stays fail-closed.

### Changed
- `docs/INSTALL.md` and `docs/TROUBLESHOOTING.md` describe cosign as an optional
  provenance layer rather than a requirement, and spell out what the digest
  guarantees without it. Platform support is stated honestly: `linux/amd64`,
  Windows via WSL2, no native Windows installer, macOS/arm64 not published.

## [0.8.0] — 2026-07-21

### Added
- **`rustok` — the shim (`cli/rustok`).** The wallet is now driven by one
  command instead of a page of container invocations: `init` (creates the
  wallet, prints the 12-word phrase and the approval PIN exactly once, and
  **refuses to run without your own terminal** so neither can leak into an
  agent's context), `connect claude|cursor|hermes` (registers the wallet as an
  MCP server with that client), `console` (the approval window — starts the
  wallet if it is not running), `start`/`stop`/`status`/`doctor`, `update` and
  `uninstall`. Wallets are discovered by label (`rustok=wallet` +
  `rustok.agent=<name>`), never by a fixed `--name`, and every agent gets its
  own keystore volume; two wallets running without `--agent` is a named refusal
  listing them, never a silent first match.
- **Keyring password can arrive as a file** — the wallet image honours the
  `RUSTOK_KEYRING_PASSWORD_FILE` convention (`podman secret …,type=mount` or a
  bind-mounted `0600` file), with named errors for a missing, non-regular or
  empty file instead of hanging on an absent password. **This needs image
  `0.8.0`+**: the previously published `v0.7.1` was built before this support
  landed, so docker's `_FILE` delivery does not work against it.
- **The wallet image is signed in CI** (keyless cosign in `wallet-publish`),
  which is what gives the installer something to verify.
- **Per-chain RPC secrets** — `connect` stores every `RUSTOK_RPC_URLS_<chain>`
  as a podman secret `rustok-rpc-<agent>-<chain>` (atomic
  `secret create --replace`; `secret rm` is banned — it succeeds silently even
  on a held secret) and both the registration and `rustok start` deliver the URL
  through that secret, so a keyed RPC URL stays out of argv, out of the agent's
  config and out of `inspect`. Docker fallback keeps the honest literal `-e`
  (documented second tier).
- **`scripts/install.sh`** — one-command installer (`curl … | sh`), a full
  rewrite of the old command-printer. It installs the `rustok` SHIM, not the
  wallet: verifies the wallet image's cosign signature against this repo's
  publishing workflow FIRST (fail-closed — nothing lands on disk until the
  image is proven), pulls it BY DIGEST (a mutable tag cannot be swapped in),
  fetches the shim from a COMMIT-SHA-pinned raw URL over `--proto '=https'
  --tlsv1.2`, installs it to `~/.local/bin` and adds the 2.3c-contract PATH
  block (`RUSTOK_NO_MODIFY_PATH` opts out; idempotent). It NEVER touches a
  secret, keystore or wallet init — creating the wallet stays a human step
  (`rustok init`) run in your own terminal, never through the pipe. The
  release-pinned digest and shim commit start as fail-closed placeholders,
  filled at release time. Hermetic test suite (stub curl/engine/cosign, no
  network) + a new CI job.

### Changed
- **`rustok update`** — pulls the current wallet image FIRST (a broken pull
  stops the run before any config is touched), then re-registers every
  rustok MCP entry across claude/cursor/hermes. Each client keeps its own
  wallet: the agent is read back out of the entry's own `rustok.agent`
  label (self-healing — no side-car state to go stale) and passes the same
  charset gate as `--agent`. The replaced entry is printed per client; a
  running wallet keeps the old image until its agent's next session start.
  The shim itself does not self-update — re-run the installer.
- **`rustok uninstall`** — data-safe teardown in reverse install order:
  deregisters from all three clients (foreign config keys untouched;
  hermes gets a timestamped backup), stops running wallets, removes the
  `rustok-keyring-*`/`rustok-rpc-*` secrets (or the docker password
  files), removes the installer's marked PATH block (`# >>> rustok
  installer >>>` … `# <<< rustok installer <<<` — the 3.2 contract; no
  markers, no touching a shell profile; a profile with duplicate markers
  is left untouched with a named warning, never blind-deleted) and
  `~/.local/bin/rustok`. **Keystore volumes are NEVER touched** without
  `--purge-keys` AND its interactive `delete my keys` confirmation read
  from /dev/tty (a pipe or blind automation gets a named refusal) — the
  one gated road through the shim to the keys.
- **Old-entry print on every replace** — the claude writer now prints the
  previous entry on a successful `--force` replace too (it used to print
  only when the re-add failed), and the hermes writer prints the replaced
  `rustok` block before writing (it used to rely on the backup file
  alone): one recovery path across all three writers, so a routine
  `update` can never swallow a hand-tuned entry silently.
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
- Registration existence is probed by reading `$HOME/.claude.json` (jq,
  read-only; user-scope only) — never `claude mcp get`/`list`, which
  health-check and thereby start a wallet container on the shared keystore.
- **The keyring password is delivered by secret or file, never inline.** Inline
  `-e` values, environment passthrough and `--env-file` are retired to a legacy
  note: the value is visible in `inspect` (and, for an env block, in the MCP
  config), and inside an env-file **quotes become part of the password** — a
  silent unlock failure that broke a real onboarding.
- **Documentation is written around the one-command install**; the by-hand
  container setup survives as an explicit appendix for anyone who will not pipe
  a script into a shell. `rustok update`'s limits are stated wherever it appears:
  it pulls by tag and does not re-run the cosign verification.

### Removed
- **`skills/rustok-wallet-tui/scripts/health-check.sh`** — an unreferenced
  leftover that taught an inline password in its header and forwarded one through
  the environment in its body. `rustok doctor` / `rustok status` do its job
  safely.

### Fixed
- **Fixed container names collided.** The agent launches the wallet itself, so a
  hard-coded `--name` failed the moment anything started a second instance (a
  health probe, an `mcp list`) — and with `--replace` it would kill a live
  wallet. Discovery is by label now.
- **Hermes could not see its wallet.** A wrapper script broke the protocol (zero
  tools). Hermes gets its own volume and sub-label, written by
  `rustok connect hermes`; the obsolete wrapper is called out for removal.
- **The MCP entry name in the docs did not match the code.** Examples registered
  `rustok-wallet-tui` while the shim writes — and looks for — `rustok`, so a
  hand-built setup was invisible to `update` and `uninstall`. The shim already
  warned about this "doc-era" entry; the docs were its source.

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

## Package reset — v1 (Rust) → v2 (Python)

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
