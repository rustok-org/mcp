# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2.0 | :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities to **security@rustok.org** (or via GitHub private vulnerability report if enabled).

**Do NOT open public issues for security bugs.**

### What to include
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Suggested fix (if any)

### Response timeline
- Acknowledgment within 48 hours
- Initial assessment within 5 business days
- Fix released as patch version within 14 days (critical) or 30 days (high)

## Release Verification

All releases are signed. Verify before installation:

```bash
# Check SHA-256 checksum
sha256sum -c rustok-agent-mcp-x86_64-linux.tar.gz.sha256

# Verify SLSA provenance (if available)
slsa-verifier verify-artifact rustok-agent-mcp \
  --provenance-path rustok-agent-mcp.intoto.jsonl \
  --source-uri github.com/rustok-org/mcp
```

## Security Measures

| Measure | Implementation |
|---------|---------------|
| Binary stripping | Symbols removed from release builds |
| Checksums | SHA-256 for all artifacts |
| Container signing | Cosign keyless via OIDC |
| Supply chain | SLSA Level 3 provenance (target) |
| Secret handling | `RUSTOK_AGENT_PASSWORD` via env var only — never logged |
