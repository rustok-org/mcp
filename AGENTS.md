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
- [ ] Docs carry no stale image tag (guarded by
      `test_every_image_tag_a_reader_can_copy_matches_the_manifest`)
- [ ] `ARG CORE_IMAGE` / `CONSOLE_IMAGE` name the intended dependency versions.
      The guard only checks their **shape** (`:vX.Y.Z`, never a floating tag) —
      whether `v0.3.1` should have become `v0.3.2` is not decidable inside this
      repo and stays a human step here

**2 — publish (ops, from `main`):**
- [ ] `gh workflow run wallet-publish.yml --ref main -f version=<X.Y.Z>` —
      **`--ref main`**, because `install.sh` pins the cosign identity to
      `@refs/heads/main`; a dispatch from a tag makes `cosign verify` reject the
      honest image for every user
- [ ] Never dispatch an already-published version (the workflow now refuses;
      `allow_existing_tag` is break-glass only — it rebuilds and replaces)
- [ ] `cosign verify` passes — **with cosign 3.x**. Our signatures are stored as
      OCI referrers, so the tag in GHCR reads `sha256-<digest>` with **no `.sig`
      suffix** and cosign 2.x reports `no signatures found` on a perfectly signed
      image. `install.sh` says so in its own error text; this line used to say
      `.sig` and cost a reviewer an hour

**3 — pin (PR):**
- [ ] `WALLET_DIGEST` = the digest just published
- [ ] `SHIM_SHA256` = `sha256sum cli/rustok` — **and it belongs in step 1, not
      here.** A content hash is computable from the working tree, so the shim and
      its pin land in the same commit; only the image digest has to wait for the
      publish. It was a commit SHA once, which could not exist before the commit
      carrying the shim — that is why the release used to need three commits and
      why its guard could never be green mid-release
- [ ] No fail-closed placeholders left in `scripts/install.sh`

**4 — tag & publish (ops):**
- [ ] Tag `wallet-tui-v<X.Y.Z>` on the step-3 merge commit — **last**, because
      the documented install command fetches `install.sh` through this tag and
      the shim beside it
- [ ] Listings refreshed (ClawHub — then re-check its audit page, Smithery,
      MCP registry); GHCR tags semver only, no `latest`. **This step is now
      load-bearing:** the landing page no longer carries an install command of
      its own, it points here, so a stale listing is a stale install for
      everyone who arrives through the front door.

**5 — the landing page (ops):** the site used to carry its own copy of the
install command, which is how it came to sit two versions behind until a third
party noticed. **It no longer names a version at all** — it points at the skill
page instead — so this step is no longer "update it", it is "confirm it did not
grow a version again".
- [ ] The page still names **no** version — this grep must come back **empty**:
      `curl -s https://rustokwallet.com/ | grep 'wallet-tui-v'`
      A match here is a regression, not a task: whoever put a version back
      created the second copy of the truth this arrangement removed.
- [ ] Nothing else to do here on an ordinary release. A change to the site is
      only needed when the *skill page link* moves, which is not a version event.

**5-bis — when the site does change (rare):** a merge is not a deploy. Vercel
blocks a build whose commit author is not the project owner (Hobby plan, no
collaborators), and a squash merge re-authors the commit to whoever opened the
PR. Commit directly to `main` with the owner as author, and then **check the
live page**, not the dashboard.
