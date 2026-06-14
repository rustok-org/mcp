# PR-7.1: de-v1-ify the mcp repo + rebuild the ClawHub skill (Python MCP)

> The `mcp` repo is a v1 Rust-skill scaffold with the new Python MCP grafted into
> `src/`+`tests/`. The whole distribution/skill/docs/CI surface still targets the
> dead v1 binary `rustok-agent-mcp` + the dropped hard-policy model, so a ClawHub
> publish today would ship a broken skill. This PR aligns the repo to the new
> Python MCP and rebuilds the publishable skill. Repo: **`mcp`** only.

## Background / architecture constraint (the key decision)

v1's ClawHub skill was **self-contained**: a single binary `rustok-agent-mcp`
that *was* the wallet (keys on the installing user's machine → true self-custody
per user). v2 split the wallet into **Core + Gateway + MCP**; the published MCP
(`rustok-mcp-stdio`) is a **thin client** that needs a Gateway+Core backend. So
the v2 ClawHub skill must pick a backend model:

- **Model 1 — self-contained local stack (RECOMMENDED).** The skill ships a
  `docker compose` (core+gateway+mcp+redis) the user runs locally; `rustok-mcp-stdio`
  (or the local MCP HTTP) talks to `localhost` gateway. Preserves v1's
  per-user self-custody (their keys, their machine). Heavier than v1's single
  binary (needs Docker), but correct for a self-custody product.
- **Model 2 — remote client to our hosted backend.** Skill = `rustok-mcp-stdio` +
  `RUSTOK_MCP_GATEWAY_URL=https://api.rustokwallet.com` + an issued Bearer key.
  Simple, but the wallet lives on *our* server (custodial — NOT user self-custody).
  Only sensible as a hosted/demo offering.

**Gate-1 question for the Captain:** Model 1, Model 2, or both (1 default)?
Everything below assumes the chosen model affects only `skills/rustok-wallet/` +
`smithery.yaml`; the rest of the cleanup is model-independent.

## D1 — model-independent cleanup (do regardless)

Remove/rewrite everything that lies about a Rust binary or the dropped policy model:

- **`.github/workflows/release.yml`** — builds a fake `rustok-agent-mcp` binary.
  Replace with a Python release flow (sdist/wheel build; optional PyPI publish on
  tag) or delete if PyPI publish is deferred.
- **`.github/workflows/docker-publish.yml`** — "Create dummy binary" step writes a
  fake `rustok-agent-mcp`. Drop that step; the Dockerfile is already Python.
- **`.github/pull_request_template.md`** — `cargo fmt/clippy/deny` → `ruff/mypy/pytest`.
- **`docs/INSTALL.md`, `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`** — rewrite
  for the Python MCP (`uvx rustok-mcp` / `pip install` / Docker image; env
  `RUSTOK_MCP_*`, `RUSTOK_MCP_GATEWAY_URL`; no `--policy-config`, no Rust tarballs).
- **`SECURITY.md`** — drop slsa/`rustok-agent-mcp` tarball verification + the
  `RUSTOK_AGENT_PASSWORD` model; document the v2 trust boundary (MCP holds no
  keys; auth via `RUSTOK_MCP_*`).
- **`CHANGELOG.md`** — add the v2 (Python MCP) entry; mark the v1 Rust history as
  superseded.

## D2 — rebuild the ClawHub skill (`skills/rustok-wallet/`) — model-dependent

- **`SKILL.md`** — full rewrite for the new tool surface (`get_wallet_context`,
  `get_balances`, `get_positions`, `preview_send`, `execute_send`, `sign_message`)
  and the chosen backend model. Remove the v1 HTTP `/context`,`/preview`,`/execute`
  curl API, the hard-policy/budget/blocklist "Safety Guarantees" (dropped — risk
  is on the user), `--policy-config`, `cargo build`, `RUSTOK_AGENT_PASSWORD`.
  Keep the MIT-0 license note (ClawHub requirement; no clean-room constraint on
  this dir).
- **`claw.json`** — bump version; fix description/permissions for the model; the
  `homepage`/tags are already fine.
- **`scripts/health-check.sh`, `examples/policy.json`** — rewrite/remove (policy.json
  is the dropped model; health-check targets the old `:3000` binary).
- **`smithery.yaml`** — replace the `rustok-agent-mcp` stdio command + the
  `RUSTOK_AGENT_PASSWORD` configSchema with `rustok-mcp-stdio` + the v2 config
  (`RUSTOK_MCP_GATEWAY_URL`, `RUSTOK_MCP_API_KEY`).

## D3 — packaging for the stdio model

- Confirm `pyproject.toml` is publishable (it is: `name=rustok-mcp`, scripts
  `rustok-mcp`/`rustok-mcp-stdio`, hatchling). Add PyPI metadata (license,
  classifiers, urls) if we publish there; otherwise document `uvx --from <git>`.
- For Model 1: add a minimal user-facing `docker-compose` (or reference meta's)
  the skill brings up; document seeding the keystore + setting RPC.

## Files (mcp)
- Rewrite: `skills/rustok-wallet/{SKILL.md,claw.json,scripts/health-check.sh}`,
  remove/rewrite `skills/rustok-wallet/examples/policy.json`, `smithery.yaml`,
  `docs/{INSTALL,CONFIGURATION,TROUBLESHOOTING}.md`, `SECURITY.md`, `CHANGELOG.md`,
  `.github/workflows/{release,docker-publish}.yml`, `.github/pull_request_template.md`.
- `pyproject.toml`: PyPI metadata (if publishing).
- No `src/` logic change (the MCP itself is done in PR-6.1 etc.).

## Acceptance
1. `rg -i 'rustok-agent-mcp|RUSTOK_AGENT_PASSWORD|cargo |policy-config'` over the
   repo returns nothing outside historical CHANGELOG notes.
2. `ruff`/`mypy`/`pytest` still green (no src change, but CI yaml valid).
3. `smithery.yaml` launches the real `rustok-mcp-stdio`; SKILL.md documents the
   real 6 tools + the chosen backend model.
4. Reviewer confirms the skill is coherent + publishable; Captain uploads via the
   ClawHub web UI.

## Out of scope
- Actual ClawHub publish (Captain, web UI). Actual PyPI publish (separate, on tag).
- Any backend/deploy change (done in the prod cutover).

## Risks
- **R1 — model decision** drives D2/D3; wrong model = wrong skill UX. Resolve at Gate-1.
- **R2 — Model 1 UX** (Docker on user machine) is heavier than v1's binary; document clearly.
- **R3 — leftover v1 references** missed → publish ships confusion. Mitigate with the rg acceptance check.
