# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities to **security@rustok.org** (or via GitHub
private vulnerability report if enabled).

**Do NOT open public issues for security bugs.**

### What to include
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Suggested fix (if any)

### Response timeline
- Acknowledgment within 48 hours
- Initial assessment within 5 business days
- Fix released as a patch version within 14 days (critical) or 30 days (high)

## Trust model

`rustok-mcp` is a thin **MCP adapter**, not the wallet. It holds **no keys and no
secrets** — it forwards tool calls over HTTP to the Rustok **Gateway**, which
talks gRPC to the **Core** (where keys live, encrypted at rest). In the
self-custody deployment the entire stack (Core + Gateway + MCP) runs on the
user's own machine; private keys never leave it.

| Measure | Implementation |
|---------|----------------|
| Key isolation | Keys live only in Core's keystore (Argon2id + AES-256-GCM); MCP/Gateway never see them |
| MCP → Gateway auth | Bearer token (`RUSTOK_MCP_API_KEY`); Gateway enforces it on `/api/v1/*` |
| Inbound MCP auth | `RUSTOK_MCP_INBOUND_API_KEY` (bearer) for the SSE/HTTP transport when exposed |
| Capability gating | Tools require `read_wallet` / `preview_tx` / `execute_tx`; fail-closed |
| Secret handling | All secrets via env / `.env` only — never logged (errors masked) |
| Transport | stdio is process-trusted (local); SSE/HTTP must run behind TLS + inbound auth |
| Container image | Python image published to GHCR; non-root runtime |

## Verifying the container image

```bash
docker pull ghcr.io/rustok-org/rustok-mcp:<version>
docker inspect ghcr.io/rustok-org/rustok-mcp:<version> --format '{{index .RepoDigests 0}}'
```

Pin by digest in production deployments.
