# Fix MCP capability grant for standard stdio clients

## Goal — one paragraph

Following `SKILL.md`/`INSTALL.md` verbatim with a standard MCP client (Claude
Desktop / Cursor) over the all-in-one stdio image yields an **empty `tools/list`**
and `-32001 "requires additional capability"` on every call. Tools are gated by
capabilities that are granted **only** via a non-standard `initialize.params.capabilities`
**list of strings**; a standard MCP client sends an *object* there (client
capabilities like `roots`/`sampling`), which parses to the empty set, so all six
tools are hidden. This contradicts the documented intent (`README.md`: "the local
**stdio** transport is process-trusted and **not gated**"). Make the stdio
transport grant all capabilities by default (process-trusted), optionally
restrictable via `RUSTOK_MCP_CAPABILITIES`, without weakening the network-facing
SSE transport.

## PR scope

- **Title:** `fix(mcp): stdio is process-trusted — grant all capabilities by default`
- **Included:**
  1. `config.py` — add `capabilities: str | None` (env `RUSTOK_MCP_CAPABILITIES`,
     empty→None via existing `_empty_to_none`).
  2. `capabilities.py` — add `resolve_stdio_capabilities(raw: str | None) -> set[Capability]`:
     unset/empty → `set(Capability)` (all, "not gated"); else parse the
     comma-separated subset via `parse_capabilities`. **If `raw` is set but parses
     to empty (typo/all-invalid), log a `WARNING` and return empty** — never
     silently re-introduce the all-gated bug without a signal (F2).
  3. `stdio.py` — seed `context = {"capabilities": resolve_stdio_capabilities(settings.capabilities)}`
     before the read loop (was `{}`).
  4. `handlers.py::handle_initialize` — override context caps **only** when the
     client provides a non-empty rustok **list** (`isinstance(raw, list)` guard);
     otherwise `context.setdefault("capabilities", set())`. Preserves the
     transport-seeded default and ignores the standard MCP capabilities *object*
     (no misparse / no warning noise).
  5. `sse.py` — same `isinstance(list)` guard at the initialize intercept so the
     standard MCP object is not misparsed. SSE stays gated-by-default (unchanged
     behavior; it is bearer-protected by design).
  6. Tests (below).
  7. Docs — minimal & accurate only: `.env.example` + `docs/CONFIGURATION.md`
     document `RUSTOK_MCP_CAPABILITIES` and that stdio defaults to all/not-gated;
     correct the `SKILL.md` capability note (stdio exposes all tools by default;
     env restricts).
- **NOT included (with explicit follow-ups):**
  - **SSE/hosted path has the same root cause** (F1): a standard MCP client over
    SSE also gets an empty `tools/list`. SSE stays gated-by-default here (it is
    network-facing + bearer-gated); granting there is a separate decision
    (host-injected caps, or an SSE default) — **deferred follow-up, not silently
    dropped**. This PR only adds the `isinstance(list)` guard to SSE so the
    standard object is not misparsed (cosmetic; no behavior change).
  - Full `README.md` v1→v2 rewrite — separate task (#3).
  - Publishing the `v*` tag / GHCR image — Captain action (#2).
  - `serverInfo.version` (0.1.0) vs `SKILL.md`/`claw.json` (0.3.0) skew (F5) —
    separate nit; not bundled into this capability PR.
  - Changing the `CAPABILITY_MAP` or tool set.

## Design rationale (F3)

The minimal bug fix is "stdio defaults to all + don't clobber the seed". The
`RUSTOK_MCP_CAPABILITIES` env is kept deliberately (not gold-plating): for a
self-custody wallet where `execute_tx` moves real funds, a **read-only agent**
(`RUSTOK_MCP_CAPABILITIES=read_wallet`) is a legitimate production safety control,
and it is the stdio/docker equivalent of "the client grants caps" — which a
standard MCP client cannot express.

## Files touched

- `src/rustok_mcp/config.py`
- `src/rustok_mcp/capabilities.py`
- `src/rustok_mcp/handlers.py`
- `src/rustok_mcp/stdio.py`
- `src/rustok_mcp/sse.py`
- `tests/test_capabilities.py`, `tests/test_handlers.py`, `tests/test_stdio.py`, `tests/test_config.py`
- `.env.example`, `docs/CONFIGURATION.md`, `skills/rustok-wallet/SKILL.md`

## Acceptance criteria — "PR is ready when..."

1. The all-in-one image launched as a standard MCP client (initialize with an
   *object* or no `capabilities`) returns **all 6 tools** in `tools/list` and
   `get_wallet_context` succeeds — no manual capability list required.
2. `RUSTOK_MCP_CAPABILITIES=read_wallet` restricts stdio to the read tools only;
   `execute_send` then returns `-32001`.
3. A client that *does* send a rustok list (e.g. `["read_wallet"]`) still has it
   honored on stdio (explicit restriction works).
4. SSE behavior unchanged: no caps granted unless the client sends the list;
   `test_sse_stores_capabilities_on_initialize` still green.
5. Backward-compat: `test_initialize_handler` (no context) and
   `test_initialize_stores_capabilities` (list) still pass.
6. `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest` all green.

## Definition of Done

- PR merged to `main`
- Branch deleted
- Tests / linter green (ruff, mypy, pytest)
- Docs updated (CONFIGURATION.md, .env.example, SKILL.md capability note)

## Test plan

- `test_resolve_stdio_capabilities_unset_is_all` — `None`/`""` → `set(Capability)`.
- `test_resolve_stdio_capabilities_subset` — `"read_wallet,preview_tx"` → that set;
  unknown tokens ignored.
- `test_resolve_stdio_capabilities_set_but_invalid_warns` — `"admin"` → empty set
  **and** a WARNING is emitted (F2; assert via `caplog`).
- `test_initialize_keeps_seeded_default_for_object` — context seeded with all caps,
  initialize params `{"capabilities": {"roots": {}}}` (object) → context unchanged
  (still all).
- `test_initialize_keeps_seeded_default_when_absent` — seeded all, no `capabilities`
  key → unchanged.
- `test_initialize_list_overrides` — seeded all, list `["read_wallet"]` → context == {READ_WALLET}.
- `test_initialize_empty_context_defaults_to_empty_set` — context `{}`, no caps →
  `context["capabilities"] == set()` (preserves old behavior).
- stdio: `test_stdio_default_exposes_all_tools` — drive `_stdio_loop`-style
  initialize+tools/list with a default-seeded context (or assert the seed) → 6 tools.
- `test_config.py` — `RUSTOK_MCP_CAPABILITIES` parsed; empty→None.
- Manual: rebuild `Dockerfile.wallet` (CORE_IMAGE=rustok-core:v0.1.0), run stdio
  handshake with `capabilities:{}` → 6 tools + `get_wallet_context` returns the
  wallet; with `RUSTOK_MCP_CAPABILITIES=read_wallet` → `execute_send` denied.
