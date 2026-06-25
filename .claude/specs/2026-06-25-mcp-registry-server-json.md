# Spec — List rustok-wallet on the official MCP Registry (Step 1: repo changes)

**Date:** 2026-06-25
**Branch:** `feat/mcp-registry-server-json`
**Mode:** solo (Engineer seat)

## Goal
Make the self-custody wallet **publishable** to the official MCP Registry
(`registry.modelcontextprotocol.io`) by landing the two repo-side artifacts the
registry validator requires. The registry is the vendor-/model-neutral hub:
clients (Cline, Cursor, VS Code, Windsurf) ingest it regardless of which LLM
drives them — so one listing cascades to the whole MCP-agent market, not just
Claude.

## Context / why now
- Decision: registry is the **first** distribution platform (max feasible reach,
  cost-no-object). Connectors-in-Claude is bigger but model-locked + gated on O1.
- Verified from the registry source (`internal/validators/registries/oci.go`,
  `docs/.../package-types.mdx`): an OCI package is rejected unless the image
  carries `LABEL io.modelcontextprotocol.server.name` whose value **equals** the
  server `name` from `server.json`.
- Verified: `wallet-publish.yml` tags images `v{{version}}` (→ `v0.1.0`), and is
  `workflow_dispatch`-only / cannot run in public CI (private `rustok-core` →
  403 at `FROM`). Wallet images are rebuilt **manually** with private-core access.

## Scope — IN (this PR, my work)
1. **`Dockerfile.wallet`** — add, in the **final `runtime` stage** (next to the
   existing `LABEL org.opencontainers.*`, lines 55-57),
   `LABEL io.modelcontextprotocol.server.name="io.github.rustok-org/rustok-wallet"`.
   The validator reads `Config.Labels` of the **published** image (verified
   `oci.go:124-135` → `img.ConfigFile().Config.Labels[...]`, a config label, not a
   manifest annotation), so it must land on the final stage, not builder/core.
2. **`server.json`** (repo root) — the registry manifest, schema `2025-12-11`:
   - `name`: `io.github.rustok-org/rustok-wallet` (GitHub-org namespace; ownership
     proven by `mcp-publisher login github`). MUST byte-match the LABEL value.
   - package `oci`, `identifier`: `ghcr.io/rustok-org/rustok-wallet:0.3.2`,
     `version`: `0.3.2`, transport `stdio`, `runtimeHint` `docker`.
   - `runtimeArguments`: `-v rustok-wallet:/data` + **two** `-e` — keystore
     password (secret) and RPC URL. `-i/--rm` are added by the client; `--init`
     is redundant (image ENTRYPOINT is tini). **`RUSTOK_ALLOWED_CHAINS` omitted**
     — the image already defaults to `1,8453` (README line 74), so the `-e` would
     duplicate the default; dropping it also reduces the same-name `-e` count.
3. **Version unification 0.1.0 → 0.3.2** (match ClawHub; see Decisions):
   - `pyproject.toml:3`, `src/rustok_mcp/main.py:52` (FastAPI),
     `src/rustok_mcp/handlers.py:69` (MCP `serverInfo`).
   - `CHANGELOG.md` — entry noting the 0.3.2 alignment + the new `server.json`.

## Decisions
- **Unified version = `0.3.2` (match ClawHub).** The skill is already 0.3.2 on
  ClawHub (live, with download history); the server/image were stuck at 0.1.0
  (`pyproject`, FastAPI app, **and the MCP `serverInfo` clients see at
  `initialize`**). Stamp the rebuilt image + registry + internal version strings
  at 0.3.2 → one number across ClawHub / serverInfo / image / registry. Avoids
  any ClawHub re-publish. Next (swap) update → `0.4.0`.
- **Tag == `version` == `0.3.2`.** Sidesteps tag≠version ambiguity. The image is
  rebuilt anyway (for the LABEL), so the Captain tags it `0.3.2` at the same time.
  Existing `v0.1.0`/`latest` tags (ClawHub/Smithery via `:latest`) stay; `:latest`
  floats to the new build.
- **LABEL value** must exactly equal `server.json` `name` — single source of truth.

## Scope — OUT (explicit)
- **Image rebuild + push** (`docker build -f Dockerfile.wallet --build-arg
  CORE_IMAGE=…private… -t ghcr.io/rustok-org/rustok-wallet:0.1.0 . && push`) —
  **Captain**, needs private-core access. My repo change alone publishes nothing.
- **`mcp-publisher login github && mcp-publisher publish`** — **Captain**.
- **`wallet-publish.yml`** — left as-is. It's disabled (private-core 403) and the
  Dockerfile LABEL covers every build path, so adding a no-`v` tag pattern there
  is dead code (can't run) — out of scope per minimum-scope.
- Other channels (Smithery, awesome-mcp-servers, PulseMCP) — separate tasks.

## Risks / open
- **Namespace grant (pre-bake gate):** `io.github.rustok-org` is baked into both
  `server.json` `name` AND the image LABEL; a wrong value wastes the manual image
  rebuild. Precedent: `github-mcp-server` publishes under the org namespace
  `io.github.github/...`, so org namespaces are supported. Definitive check =
  Captain's `mcp-publisher login github` (as `rustok-org` admin) BEFORE the
  image is rebuilt with the LABEL.
- **Multi-`-e` rendering (verify gate):** `github-mcp-server` uses one `-e`; we use
  two. Before relying on it, test-install via one real client (Cline/Cursor) and
  confirm both env vars reach the container — if the keystore password `-e` is
  dropped by the client, the wallet cannot unlock.
- If the registry rejects the image for not being anonymously pullable: pre-check
  is the Captain's anonymous `docker pull ghcr.io/rustok-org/rustok-wallet:0.1.0`
  before `mcp-publisher publish`.
- One-click install hits the no-keystore case (entrypoint exits ~60s without
  `create-wallet`). Mitigated only by `websiteUrl` → README onboarding; accepted
  as a known UX gap (server.json can't express a one-time onboarding step).
- **Reversibility:** the registry supports version deprecation; a self-custody
  listing is low-risk to retract if needed (Captain's step).

## Verification (before "готово")
- **Re-validate the FINAL** `server.json` (after dropping the chains `-e`) against
  the official schema `2025-12-11` (Draft-07) via `uv run --with jsonschema` →
  expect VALID (command + output attached in report). The PR #47 "VALID" is stale.
- `LABEL` value === `server.json` `name` (grep both, show byte-equality).
- **No stray `version = "0.1.0"`** left in the active surfaces (`pyproject.toml`,
  `main.py`, `handlers.py`, `server.json`) — grep clean; CHANGELOG *history*
  keeps its 0.1.0 references untouched (record, not a live version).
- `git diff` = the expected file set (`Dockerfile.wallet`, `server.json`,
  `pyproject.toml`, `main.py`, `handlers.py`, `CHANGELOG.md`); no other.
- Repo CI unaffected — `ci.yml` runs ruff/mypy/pytest (Python) + shellcheck on
  `scripts/*.sh` only; neither changed file is Python or a shell script, and there
  is no Dockerfile lint (no hadolint).

## Handoff after merge
Captain: rebuild+push image `:0.1.0` (with LABEL) → anon `docker pull` check →
`mcp-publisher publish`. Then verify the listing resolves on
registry.modelcontextprotocol.io.
