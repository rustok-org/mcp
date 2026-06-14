# PR-7.1b: self-custody wallet — single stdio all-in-one image + ClawHub skill

> Supersedes the skill half of `2026-06-14-de-v1-ify-skill.md`. Approved design
> (see that PR's /check "Verified plan"): ship the self-custody wallet as ONE
> self-contained **stdio** image `ghcr.io/rustok-org/rustok-wallet`, distributed
> as the skill via a `docker run -i` command. Works for ClawHub, Smithery, and
> Claude Desktop (all consume MCP over stdio). Repo: **`mcp`**.

## Why (recap)
v2 split the wallet into Core+Gateway+MCP for the *hosted* multi-client case. For
a *single local user* the gateway's network auth/rate-limit is moot and redis is
optional. v1's winning UX was one self-contained thing run locally. So: one image
that runs the whole stack and speaks MCP on stdio. Source stays private (only the
compiled `rustok-core` binary image is consumed). No service code change —
packaging only.

## D1 — all-in-one image (`mcp/Dockerfile.wallet`)
Multi-stage:
- `FROM ghcr.io/rustok-org/rustok-core:${CORE_VERSION} AS core` — source of the
  compiled `core-server` + `gateway` binaries (public binary image; private source).
- Runtime `FROM` the Python MCP base (reuse `mcp`'s existing Dockerfile output or
  a slim Python image with the mcp package installed via uv), then
  `COPY --from=core /usr/local/bin/{core-server,gateway} /usr/local/bin/`.
- Install `tini` (or document `--init`) for PID-1 signal/zombie handling.
- `ENTRYPOINT ["/usr/local/bin/rustok-wallet-entrypoint"]`.

## D2 — entrypoint (`rustok-wallet-entrypoint`)
- `create-wallet` subcommand: `exec core-server create-wallet` (PR-7.3) → shows
  the 24-word mnemonic on the user's TTY (`docker run -it … create-wallet`), exit.
- default (serve): 
  1. start `core-server` (bg, `RUSTOK_GRPC_ADDR=127.0.0.1:50051`, no redis →
     audit disabled);
  2. start `gateway` (bg, `RUSTOK_GATEWAY_ADDR=127.0.0.1:3000`,
     `RUSTOK_CORE_ADDR=http://127.0.0.1:50051`, **auth off** — in-container
     localhost, single user);
  3. **wait for gateway `/health` → core `serving`** (bounded poll, fail-fast on
     timeout) before exposing MCP;
  4. `exec rustok-mcp-stdio` (`RUSTOK_MCP_GATEWAY_URL=http://127.0.0.1:3000`) —
     its stdin/stdout become the container's MCP channel.
- On MCP exit (client closes stdin) the container stops; `--rm` + `tini` reap the
  bg core/gateway. Logs (core/gateway/mcp) go to **stderr** only (stdout is the
  JSON-RPC channel — must stay clean).

## D3 — publish (`mcp/.github/workflows/` — extend or new)
Build + push `ghcr.io/rustok-org/rustok-wallet` on `v*` tags (amd64; arm64 later),
SHA-pinned actions, `packages: write`. Build needs the `rustok-core` image
available (public, or CI authenticated). Proprietary `licenses` label.

## D4 — skill files (`skills/rustok-wallet/`)
- **`smithery.yaml`**: `command: docker`, `args: [run, -i, --rm, --init, -v,
  rustok-wallet:/data, -e, RUSTOK_KEYRING_PASSWORD, ghcr.io/rustok-org/rustok-wallet:vX]`;
  configSchema requires `RUSTOK_KEYRING_PASSWORD`. (Replaces the dead
  `rustok-agent-mcp` stdio.)
- **`claw.json`**: bump version; describe the docker-stdio run + the 6 tools.
- **`SKILL.md`**: rewrite — (a) **onboarding** (one-time, manual, foreground):
  `docker run -it --rm -v rustok-wallet:/data -e RUSTOK_KEYRING_PASSWORD=… 
  ghcr.io/rustok-org/rustok-wallet:vX create-wallet` → back up the 24 words; (b)
  the 6 tools (`get_wallet_context`, `get_balances`, `get_positions`,
  `preview_send`, `execute_send`, `sign_message`); (c) self-custody framing, no
  policy/budget. Remove the v1 curl `/context`/`/preview` API + `--policy-config`.
- **`scripts/health-check.sh`**: rewrite or drop (no standalone HTTP service).

## D5 — docs + leftover de-v1-ify (the remainder from PR-7.1a)
- `docs/{INSTALL,CONFIGURATION,TROUBLESHOOTING}.md`: rewrite for the single-image
  flow (Docker prereq, onboarding, the stdio command, env, recovery).
- `scripts/install.sh`: replace the Rust-binary installer with a tiny helper that
  prints the docker pull/run/onboarding commands (or remove + fold into docs).
- `.github/workflows/test-distribution.yml`: drop the install.sh shellcheck/syntax
  jobs that targeted the v1 installer; keep/extend the docker smoke (build the
  wallet image, run `--help`/a stdio `initialize` round-trip).
- `pyproject.toml`: PyPI metadata is **optional** (the image embeds mcp; `uvx`
  not required for the skill). Defer.

## Acceptance
1. `docker build -f Dockerfile.wallet` produces an image that, on `create-wallet`,
   prints a 24-word mnemonic + address; on default run, answers an MCP
   `initialize` + `tools/call get_positions` over stdio (verified locally against
   the local `rustok-core:v0.1.0` image + a real mainnet RPC).
2. stdout carries only JSON-RPC (logs on stderr); container exits cleanly on EOF.
3. `smithery.yaml`/`claw.json`/`SKILL.md` reference the real image + 6 tools +
   onboarding; no `rustok-agent-mcp`/policy leftovers (`rg` clean).
4. CI green; SHA-pinned; proprietary label.

## Out of scope / preconditions
- **Owner steps:** publish + Public the `rustok-core` AND `rustok-wallet` images
  (tag + EULA + visibility) for the public live test; confirm ClawHub accepts a
  `docker`-stdio skill command (else fall back to documenting the manual run).
- arm64 (later); PyPI publish (later); migration notice for ~323 v1 users (D6 below).

## D6 — migration notice
Short note (CHANGELOG + skill README): the v2 skill is a breaking change (Docker
required, new onboarding); v1 installs keep working until users migrate.

## Risks
- **R1 — stdout cleanliness:** any core/gateway/mcp stdout line corrupts JSON-RPC.
  Force all service logs to stderr (mcp already does; verify gateway/core respect
  it — they log JSON to stderr via tracing). Test the stdio round-trip.
- **R2 — readiness race:** MCP must not accept calls before gateway/core are up →
  the entrypoint health-wait (D2.3) gates it.
- **R3 — build needs the core image:** local build uses the local
  `rustok-core:v0.1.0`; CI needs it published/authenticated.
- **R4 — signal/zombie handling:** use `tini`/`--init` so bg core/gateway are
  reaped and SIGTERM propagates.
- **R5 — ClawHub docker-stdio support** unverified — confirm with the owner;
  fallback = manual `docker run` documented in SKILL.md.
