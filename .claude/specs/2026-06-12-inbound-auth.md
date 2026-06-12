# MCP incoming authentication (unblocks PR-5.1)

> Context: PR-5.1 (TLS reverse proxy, repo `meta`) is frozen — it would expose
> `mcp:3001` publicly, but the SSE transport currently authenticates no inbound
> client (`sse.py:26`, `sse.py:65`). This task adds inbound auth so MCP is safe
> to expose. Reviewer verdict 2026-06-12: Option 2 (auth in the app, then TLS).

## Goal — one paragraph

Require a bearer token on the network-facing MCP transport (SSE) so only callers
holding the configured secret can open a session or post JSON-RPC. The token is
checked in constant time; `/health` stays public; the stdio transport (local,
process-trusted) is unchanged. This closes the inbound trust boundary that
PR-5.1 depends on.

## Current state (verified)

- `GET /mcp/sse` (`sse.py:26`) creates a session for any caller — no auth.
- `POST /mcp/message` (`sse.py:65`) looks a session up by UUID only — no auth.
- `RUSTOK_MCP_API_KEY` (`config.py:17`) is the *outbound* MCP→Gateway key
  (`gateway.py:31`), NOT an inbound credential.
- `/health` (`health.py:15`) is consumed by the compose healthcheck — must stay open.
- stdio (`stdio.py`) is a local transport — out of scope for network auth.

## Design decisions (need Gate 1 sign-off)

### D1 — Separate inbound secret (recommended)

New setting `inbound_api_key: str | None` → env `RUSTOK_MCP_INBOUND_API_KEY`
(prefix-consistent). Kept distinct from the outbound `api_key`. Rationale:
two different trust boundaries (client→MCP vs MCP→Gateway) must not share one
secret (`security.md`: "API keys minimally scoped"). Rejecting reuse of
`RUSTOK_MCP_API_KEY`.

### D2 — Enforcement model: optional + warn (recommended), enforced publicly by PR-5.1

- If `inbound_api_key` is set → every request to `/mcp/*` must carry
  `Authorization: Bearer <key>`; constant-time compare (`secrets.compare_digest`);
  mismatch/absent → `401` with a generic body.
- If `inbound_api_key` is unset → requests pass, and the server logs a startup
  warning (mirrors the Gateway pattern, `core/.../main.rs:27`). This keeps the
  loopback dev flow (`docker compose up`) working with no token.
- The "never expose publicly without a key" guarantee is enforced one layer up
  in **PR-5.1**: Caddy injects a required `RUSTOK_MCP_INBOUND_API_KEY`, and
  PR-5.1 acceptance tests a `401` for an unauthenticated request through Caddy.
- **Alternative considered (strict):** refuse to start when bound to a
  non-loopback host without a key. Rejected for this PR — host/exposure is a
  deploy concern the app can't reliably detect (it always binds `0.0.0.0`
  inside its container); enforcing it here gives false security. Open for
  Reviewer to overrule.

### D3 — Mechanism: FastAPI dependency, not in-function check

A `require_auth` dependency applied to the SSE router (`dependencies=[...]` on
`APIRouter(prefix="/mcp")`). Reason: keeps auth out of handler bodies, and
existing unit tests that call `mcp_sse`/`mcp_message` directly keep working
(router-level dependency is not invoked on direct function calls); integration
tests via the `client` fixture cover 401/200.

Constraints settled at Gate 1 (from /check):
- **Resolve settings at request time.** `require_auth` calls `get_settings()`
  inside the request, never captures the key at import — otherwise the `client`
  fixture (module-level `app` + `clear_settings_cache`) cannot toggle key
  state in tests.
- **Status code = 401.** Use `HTTPBearer(auto_error=False)` (keeps the Swagger
  "Authorize" button / OpenAPI scheme) + a manual `raise HTTPException(401,
  "Unauthorized")`. `auto_error=True` raises 403 — verified default — which
  contradicts acceptance criterion 1.
- **`/health` is unaffected** — verified: `health.py` mounts `APIRouter()` with
  no prefix, the dependency is attached only to the `/mcp` router. No structural
  way for it to gate `/health`; covered by a single no-regression assertion.

### D4 — Transport / header assumptions (from /check)

- Auth is carried in the `Authorization: Bearer` request header. The MCP SSE
  consumers (agent runtimes, not browser `EventSource`) send request headers;
  browser `EventSource` cannot and is not a supported client here.
- **Query-string tokens are forbidden** — they leak into access logs
  (`security.md`: no sensitive data in logs). Documented in README.

### D5 — Empty-string env normalization (from /check)

`RUSTOK_MCP_INBOUND_API_KEY=` (set but empty) is normalized to `None`
(treated as "no key configured") via a field validator, so an empty value can
never be mistaken for enabled auth or match an empty client token. Asserted by
a test.

## PR scope

- **Title:** `feat: bearer auth on the SSE transport`
- **Repo:** `mcp` only.
- **Included:**
  1. `config.py`: add `inbound_api_key: str | None = None`
     (env `RUSTOK_MCP_INBOUND_API_KEY`) + validator normalizing `""` → `None` (D5).
  2. New `src/rustok_mcp/auth.py`: `require_auth` FastAPI dependency —
     `HTTPBearer(auto_error=False)`, `secrets.compare_digest` against the
     request-time `inbound_api_key`, raises `401` (generic detail) on
     mismatch/absent; passes when no key configured (D2/D3).
  3. `sse.py`: attach `require_auth` to the `/mcp` router (covers `/sse` and
     `/message`).
  4. `main.py`: log a startup warning when `inbound_api_key` is unset.
  5. `.gitignore`: add `.env`, `.env.*`, keep `!.env.example` — **blocking**
     security gate (`security.md` pre-commit), currently absent.
  6. `.env.example` (new — verified absent): document
     `RUSTOK_MCP_INBOUND_API_KEY` + existing `RUSTOK_MCP_*` settings,
     placeholders only.
  7. `README.md`: short "Authentication" section — inbound vs outbound key,
     dev (no key) vs prod (required), stdio exemption, header-not-query rule (D4).
  8. Tests:
     - `test_config.py`: `inbound_api_key` read from prefixed env / defaults
       None / **empty-string `""` → None** (D5).
     - `test_auth.py` (new): dependency unit tests — valid token, wrong token,
       missing header, malformed/`Basic` header, empty Bearer token,
       no-key-configured pass-through; `compare_digest` path exercised.
     - `test_sse.py`: integration via `client` — `/mcp/sse` and `/mcp/message`
       return `401` without token / success with token when key set; still
       open when key unset.
     - `test_health.py`: single assertion — `/health` stays `200` without a
       token when a key is configured (no-regression; structurally clean per D3).
- **Explicitly NOT included:**
  - Per-client / per-capability tokens, token rotation, JWT (static shared
    secret only — matches v1 and current threat model).
  - stdio auth (local transport).
  - Rate limiting (Gateway already rate-limits; revisit in PR-5.2).
  - Capability hardening (self-declared capabilities) — noticed, separate task.
  - Any change in `core`/`meta` repos (PR-5.1 wiring is its own resumed PR).

## Files touched

| File | Change |
|---|---|
| `src/rustok_mcp/config.py` | + `inbound_api_key` |
| `src/rustok_mcp/auth.py` | new — `require_auth` dependency |
| `src/rustok_mcp/sse.py` | apply dependency to `/mcp` router |
| `src/rustok_mcp/main.py` | startup warning when unset |
| `.gitignore` | + `.env`, `.env.*`, `!.env.example` |
| `.env.example` | new |
| `README.md` | Authentication section |
| `tests/test_config.py`, `tests/test_auth.py`, `tests/test_sse.py`, `tests/test_health.py` | tests |

## Acceptance criteria — "PR is ready when..."

1. Key set: `GET /mcp/sse` and `POST /mcp/message` without a valid
   `Authorization: Bearer` → `401`; with it → normal behavior.
2. Key unset: both endpoints behave as today (open) + one startup warning.
3. `/health` → `200` regardless of token, in both modes.
4. Token compare uses `secrets.compare_digest` (no early-exit string ==).
5. stdio path unchanged.
6. Empty `RUSTOK_MCP_INBOUND_API_KEY=` behaves as unset, not as enabled-auth (D5).
7. Unauthenticated/missing-header request → `401` (not 403).
8. `.gitignore` covers `.env` (security gate).
9. Gates green: `ruff check`, `ruff format --check`, `mypy`, `pytest` (incl. new tests).
10. `/security-review` run on the diff — no blockers.

## Definition of Done

- PR merged to `main` (squash), branch deleted.
- Gates + `/security-review` evidence in the Gate 2 report.
- Unblocks PR-5.1 resume conditions 1 (auth PR merged).

## Test plan

1. `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -q` — all green.
2. New auth unit tests: 5 cases above.
3. SSE integration: 401 without / success with token (key set); open (key unset).
4. Health no-regression test.
5. `/security-review` on the final diff; address findings before report.
