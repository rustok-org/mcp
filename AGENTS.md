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

- [ ] Version bumped in `CHANGELOG.md`
- [ ] `pyproject.toml` version matches release tag
- [ ] Docker image builds and runs
- [ ] Checksums generated for all artifacts
- [ ] GHCR tags: semver only, no `latest`
