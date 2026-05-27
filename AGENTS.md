# AGENTS.md — Rustok MCP

> Overrides `meta/AGENTS.md` for `mcp/` subtree.
> This is a **distribution repository** — no wallet source code lives here.

---

## Stack

- **Purpose:** Distribution layer — install scripts, Docker, CI/CD, docs
- **License:** MIT-0 (scripts and docs only)
- **Binary source:** Private `rustok-org/core` workspace

---

## Repository Rules

1. **No source code** — The MCP agent binary is built in the private core repo and published here as a release artifact. Do not add Rust source files that implement wallet logic.
2. **Scripts must be POSIX-compliant** — `install.sh` targets Linux, macOS, Windows (Git Bash). Test with `shellcheck`.
3. **Docker security** — Non-root user, read-only root fs, distroless base image where possible.
4. **No `latest` tag** — GHCR tags must be semver only (`v0.2.0`, `v0.2`, `v0`).
5. **Checksum verification** — Every release artifact must have SHA-256 checksum. Install script verifies it.

---

## CI/CD Architecture

```
Private core repo (rustok-org/core)
    ↓ push tag v*
    ↓ Build release binary
    ↓ Publish to public mcp repo Releases (via PAT)

Public mcp repo (rustok-org/mcp)
    ↓ Release published
    ↓ Docker image built from binary
    ↓ GHCR push
```

**Security invariant:** Public CI never accesses private code. Private CI pushes to public repo with limited-scope PAT (`contents:write` only).

---

## Gates

```bash
# Shell scripts
shellcheck scripts/*.sh

# Docker
docker build -t rustok-mcp .
docker run --rm rustok-mcp --help

# Markdown (optional)
npx markdownlint-cli docs/*.md *.md
```

---

## Release Checklist

- [ ] Version bumped in `CHANGELOG.md`
- [ ] `install.sh` URL points to correct release
- [ ] Docker image builds and runs
- [ ] Checksums generated for all artifacts
- [ ] GHCR tags: semver only, no `latest`
