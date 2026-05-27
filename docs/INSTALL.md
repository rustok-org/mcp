# Installation Guide

## Prerequisites

- For **binary install**: `curl`, `tar` or `unzip`, `sha256sum` or `shasum`
- For **Docker**: Docker Engine 20.10+
- For **build from source**: Access to private core repository (maintainers only)

---

## Option A: One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/rustok-org/mcp/main/scripts/install.sh | bash
```

### What it does
1. Detects your OS and architecture
2. Downloads the latest release from GitHub Releases
3. Verifies SHA-256 checksum
4. Installs to `~/.local/bin/` (or `$INSTALL_DIR`)
5. Verifies the binary runs

### Supported platforms

| OS | Architecture | Artifact |
|----|-------------|----------|
| Linux | x86_64 | `rustok-agent-mcp-x86_64-linux.tar.gz` |
| Linux | arm64 | `rustok-agent-mcp-aarch64-linux.tar.gz` |
| macOS | Apple Silicon | `rustok-agent-mcp-aarch64-darwin.tar.gz` |
| macOS | Intel | `rustok-agent-mcp-x86_64-darwin.tar.gz` |
| Windows | x86_64 | `rustok-agent-mcp-x86_64-windows.zip` |

### Custom install directory

```bash
INSTALL_DIR=/usr/local/bin curl -fsSL ... | bash
```

---

## Option B: Docker

### Quick start

```bash
docker run -p 127.0.0.1:3000:3000 \
  -v ~/.rustok/agent:/data \
  -e RUSTOK_AGENT_PASSWORD="your-strong-password" \
  ghcr.io/rustok-org/rustok-mcp:v0.2
```

### With docker-compose

See [`docker-compose.yml`](../docker-compose.yml) in this repository.

```bash
docker-compose up -d
```

### Security notes

- The container runs as non-root user (`uid=1000`)
- Use `--read-only` for additional hardening
- Mount a named volume for persistent data:
  ```bash
  docker volume create rustok-data
  docker run ... -v rustok-data:/home/rustok/.rustok/agent ...
  ```

---

## Option C: Manual download

1. Go to [GitHub Releases](https://github.com/rustok-org/mcp/releases)
2. Download the artifact for your platform
3. Verify checksum:
   ```bash
   sha256sum -c rustok-agent-mcp-x86_64-linux.tar.gz.sha256
   ```
4. Extract and move to your PATH:
   ```bash
   tar xzf rustok-agent-mcp-x86_64-linux.tar.gz
   mv rustok-agent-mcp ~/.local/bin/
   chmod +x ~/.local/bin/rustok-agent-mcp
   ```

---

## Option D: Build from source (maintainers only)

This requires access to the private `rustok-org/core` repository.

```bash
git clone https://github.com/rustok-org/core.git
cd core
cargo build --release --bin rustok-agent-mcp
```

---

## Verify installation

```bash
rustok-agent-mcp --help
rustok-agent-mcp --version
```

## Next steps

- [Configuration](CONFIGURATION.md) — Set up policies, chains, API keys
- [Troubleshooting](TROUBLESHOOTING.md) — Common issues and fixes
