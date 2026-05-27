# AGENTS.md — Rustok MCP Server

> Overrides `meta/AGENTS.md` for `mcp/` subtree.
> Read `meta/AGENTS.md` first, then this file.

---

## Stack

- **Language:** Rust 2021, MSRV 1.85
- **HTTP:** Axum 0.7
- **Serialization:** serde + serde_json
- **CLI:** clap v4
- **Standard:** `~/Workspace/Codex/standards/rust.md`

---

## Dual Transport

| Mode | Use Case | Security |
|------|----------|----------|
| **HTTP** | Remote orchestration, cloud deployment | Bearer auth + rate limiting |
| **stdio** | Claude Desktop, Cursor, local AI | No auth (local process) |

Both modes share the same request/response DTOs and business logic.

---

## Key Rules

- **No own keystore** — use `core` keyring via capability tokens
- **Capability-based permissions** — each tool call checks capability scope
- **JSON-RPC 2.0** over stdio — handle notifications silently
- **Graceful shutdown** — `tokio::signal` for both transports
- **Structured logging** — `tracing` with request IDs

---

## CI Gates

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo nextest run --workspace
docker build -t rustok-mcp .
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | timeout 5 ./target/release/rustok-mcp --transport stdio
```

---

## Protocol Compliance

- Must pass MCP Inspector validation
- Tools manifest exposed via `tools/list` endpoint
- All tool calls return structured `Content` array
- Errors return `jsonrpc` error objects, never panic
