# AGENTS.md — Rustok MCP

> Overrides `meta/AGENTS.md` for `mcp/` subtree.
> This repo now hosts the **Python MCP Server** implementation.

---

## Stack

- **Language:** Python 3.12+
- **Framework:** FastAPI 0.115+ with SSE and stdio transports
- **Package manager:** uv
- **Key deps:** `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`
- **Standards:** `~/Workspace/Codex/standards/python.md` + `~/Workspace/Codex/standards/fastapi.md`

---

## Repository Rules

1. **No secrets in source** — API keys, tokens, passwords only via env vars (`RUSTOK_MCP_*`).
2. **Scripts must be POSIX-compliant** — `install.sh` targets Linux, macOS, Windows (Git Bash). Test with `shellcheck`.
3. **Docker security** — Non-root user, read-only root fs where possible, distroless or slim base image.
4. **No `latest` tag** — GHCR tags must be semver only (`v0.2.0`, `v0.2`, `v0`).
5. **Checksum verification** — Every release artifact must have SHA-256 checksum. Install script verifies it.

---

## Architecture

The MCP Server is a thin JSON-RPC adapter between LLM agents (Claude Desktop, Cursor, cloud agents) and the Rustok Gateway.

```
Claude Desktop (stdio)  →  MCP Server (Python)  →  Gateway (Axum)  →  Core (Rust)
Cloud agent (SSE)       →  /mcp/sse
```

- **No wallet logic here** — all crypto, signing, and key material lives in `core/`.
- **No persistent state** — MCP Server is stateless; state lives in Gateway / Core.
- **Capability-based security** — client selects capabilities on connect (`read_wallet`, `preview_tx`, `execute_tx`).

---

## Gates

```bash
# Python
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest

# Shell scripts
shellcheck scripts/*.sh
```

---

## Release Checklist

The order below is not style — it is the only order that assembles. The image
digest does not exist until the publish runs, the publish requires the bumped
version already on `main`, and the git tag must land on the commit that carries
the filled pins, because users fetch `install.sh` **by tag**. A tag cut before
the pins are filled is dead permanently.

**1 — prep (PR):**
- [ ] Version bumped in every point (`tests/test_version_consistency.py` enforces
      the set: `pyproject.toml`, skill frontmatter, `claw.json`,
      `WALLET_VERSION`, the `DEFAULT_IMAGE` tag)
- [ ] `CHANGELOG.md` describes the release — including anything user-facing that
      landed since the last tag, not only the last PR
- [ ] Docs carry no stale image tag

**2 — publish (ops, from `main`):**
- [ ] `gh workflow run wallet-publish.yml --ref main -f version=<X.Y.Z>` —
      **`--ref main`**, because `install.sh` pins the cosign identity to
      `@refs/heads/main`; a dispatch from a tag makes `cosign verify` reject the
      honest image for every user
- [ ] Never dispatch an already-published version (the workflow now refuses;
      `allow_existing_tag` is break-glass only — it rebuilds and replaces)
- [ ] `cosign verify` passes and a `.sig` tag appeared in GHCR

**3 — pin (PR):**
- [ ] `WALLET_DIGEST` = the digest just published; `SHIM_COMMIT` = the merge
      commit from step 1 (it carries the bumped `DEFAULT_IMAGE`)
- [ ] No fail-closed placeholders left in `scripts/install.sh`

**4 — tag & publish (ops):**
- [ ] Tag `wallet-tui-v<X.Y.Z>` on the step-3 merge commit — **last**
- [ ] `sha256` of `install.sh` at that tag published in the release notes
- [ ] Release notes state compatibility and migration (the shim chooses the image
      version; an old shim keeps users on an old image whatever `update` prints)
- [ ] Listings refreshed (ClawHub — then re-check its audit page, Smithery,
      MCP registry); GHCR tags semver only, no `latest`
