# PR-5.2c: MCP instrumentation — traces + structured logs, full MCP→Gateway→Core chain

> Roadmap: Phase 5, PR-5.2 (decomposed 5.2a/b/c/d). Depends on PR-5.2a (obs backend)
> and PR-5.2b (core/gateway instrumentation, merged: core#47, meta#17).
> Repos touched: **`mcp`** (Python OTel) + **`core`** (gateway inbound HTTP traceparent
> extract) + **`meta`** (obs overlay env/network for mcp).
> Gate-1 decisions (Captain, 2026-06-13): **auto-instrumentation**
> (FastAPIInstrumentor + HTTPXClientInstrumentor); mode = **team** (Reviewer online).

## Goal — one paragraph

Make a request flowing **MCP → Gateway → Core** a single distributed trace in Tempo, and
give MCP structured JSON logs carrying `trace_id` (Loki correlation) — closing the e2e
trace-in-Grafana gate. MCP creates a server span per request, propagates the W3C trace
context over HTTP to the Gateway, the Gateway continues that trace (new in this PR), and on
to Core (already wired in 5.2b). Export is **opt-in**: with no `RUSTOK_OTLP_ENDPOINT` (the
default), MCP emits JSON logs only — no exporter, no network — mirroring 5.2b's contract.

## Out of scope

- **Metrics / `/metrics`** — PR-5.2d (gateway + mcp `/metrics`, Prometheus pull).
- Any change to MCP business logic, the JSON-RPC protocol, tool semantics, or auth.
- Postgres — PR-5.3.

## D1 — Gateway must EXTRACT inbound HTTP traceparent (core change, required)

In 5.2b the Gateway was the trace **root**: `gateway/src/lib.rs` `build_router` creates the
`http_request` span (`TraceLayer::make_span_with`) but does **not** read a `traceparent`
header. So today an incoming MCP request would start a **new** trace at the Gateway, breaking
the MCP→Gateway link. This PR adds inbound HTTP extraction (symmetric to the gRPC
`link_remote_parent` from 5.2b):
- In `make_span_with`, build the `http_request` span, then extract the parent context from the
  request headers via a `HeaderExtractor` (opentelemetry `Extractor` over `http::HeaderMap`,
  hand-rolled in `gateway/src/otel_meta.rs` — no new dep) and `set_parent` **before** the span
  is entered (the 5.2b rule: set_parent after enter does not link the trace_id).
- Missing/invalid `traceparent` → Gateway stays a trace root (best-effort; never affects the
  request). Requires the global propagator, already installed by `init_telemetry` when OTLP is
  on.
- Result: the Gateway `http_request` span (and its child handler spans + the gRPC client
  inject) all carry MCP's trace_id → one trace MCP→Gateway→Core.

## D2 — Python auto-instrumentation

- `FastAPIInstrumentor.instrument_app(app, excluded_urls="health")` — server span per request +
  **auto-extract** of the incoming `traceparent` (W3C is the OTel Python default propagator).
  **`/health` is excluded** (check finding 3): the Docker healthcheck hits it every 30s and would
  otherwise spam Tempo with a span per probe.
- `HTTPXClientInstrumentor().instrument()` — client span per outbound call + **auto-inject** of
  `traceparent` into the Gateway request (the single `httpx.AsyncClient` in `gateway.py`).
- Avoids manual span/propagator code; covers all current and future endpoints/calls.
- **Idempotency:** instrument once (guard against double-instrument if `init_telemetry`/app
  import runs twice, e.g. in tests) — instrumentors warn/error on re-instrument.

## D3 — OTLP/HTTP export, opt-in, graceful degradation (mirror 5.2b)

- Exporter: `opentelemetry-exporter-otlp-proto-http` → **`<RUSTOK_OTLP_ENDPOINT>/v1/traces`**.
  As in 5.2b, the constructor `endpoint=` is the **full** per-signal URL (Python does NOT append
  `/v1/traces` for a constructor endpoint — only for the `OTEL_EXPORTER_OTLP_ENDPOINT` env base),
  so build `<base>/v1/traces` explicitly.
- `RUSTOK_OTLP_ENDPOINT` is read **un-prefixed** (NOT `RUSTOK_MCP_*`) for parity with core and
  the obs overlay. Unset/empty → no exporter, no TracerProvider with OTLP, JSON logs only.
  Malformed (non-`http(s)://`) → fail fast at startup. **Redact URL userinfo** (`user:pass@`)
  before logging the endpoint or putting it in an error — parity with 5.2b M1 (finding 4).
- `BatchSpanProcessor` (OTel Python default is non-blocking, background thread) so export never
  adds latency to a request.
- `service.name` = `get_settings().app_name` (already `"rustok-mcp"`, finding 6) — not hardcoded.

## D4 — Structured JSON logs with trace_id (mirror 5.2b D6)

- JSON formatter on **stderr**. **Hard invariant (finding 1):** in **stdio mode, neither
  `logging` nor any OTel diagnostic may write to stdout** — stdout carries the JSON-RPC framing
  (`stdio.py` `print(..., flush=True)`); a stray stdout line corrupts the protocol. All log
  handlers target `sys.stderr`; assert this in a stdio test.
- **uvicorn integration (finding 5):** `main.py:run()` calls `uvicorn.run(...)`, which installs
  its own loggers via `log_config`. A bare `logging.basicConfig` is overridden. Pass a JSON
  `log_config` to `uvicorn.run` (or configure `dictConfig` covering `uvicorn`/`uvicorn.access`)
  and verify at CODE the emitted lines are JSON.
- Inject `trace_id`/`span_id` into records via `LoggingInstrumentor` (adds
  `otelTraceID`/`otelSpanID`) **or** a custom formatter reading the current span context —
  decide at CODE; verify fields are present (empty when no active span). Logs during a request
  carry the trace_id (Loki↔Tempo).
- Respect the existing `log_level` setting (`RUSTOK_MCP_LOG_LEVEL` / `log_level`); no RUST_LOG.

## D6 — Tooling: mypy strict + ruff (finding 2)

`mcp` CI runs `ruff check/format src tests` and **`mypy src` with `strict = true` +
`warn_unused_ignores = true`** (`pyproject.toml`). OTel contrib instrumentation packages
(`opentelemetry.instrumentation.{fastapi,httpx,logging}`) are not fully stub-complete →
strict mypy errors with "missing library stub". Add a scoped
`[[tool.mypy.overrides]] module = ["opentelemetry.instrumentation.*"]
ignore_missing_imports = true` rather than inline `# type: ignore` (which `warn_unused_ignores`
would reject when unneeded). At CODE, confirm which packages ship `py.typed` and narrow the
override to only those that need it. New code (`telemetry.py`) must pass strict mypy and ruff
(src **and** tests).

## D5 — stdio transport

`stdio.py` is a separate entrypoint (local MCP clients, no HTTP server). It also builds a
`GatewayClient`. Telemetry init is shared so stdio gets httpx client spans + JSON logs when an
endpoint is set, but **no FastAPI server span** (no HTTP server). Initialise telemetry in both
entrypoints via one helper; only `main.py` calls `instrument_app`.

## Package additions (`pyproject.toml`)

Grounded against PyPI (2026-06-13); exact pins resolved by `uv` at CODE:

| Package | Version | Role |
|---|---|---|
| `opentelemetry-sdk` | `~=1.42` | TracerProvider, BatchSpanProcessor, Resource |
| `opentelemetry-exporter-otlp-proto-http` | `~=1.42` | OTLP/HTTP span exporter |
| `opentelemetry-instrumentation-fastapi` | `~=0.63b0` | server span + inbound traceparent extract |
| `opentelemetry-instrumentation-httpx` | `~=0.63b0` | client span + outbound traceparent inject |
| `opentelemetry-instrumentation-logging` | `~=0.63b0` | trace_id/span_id in log records (if used for D4) |

(API/SDK on the `1.x` line; contrib instrumentation on the aligned `0.63bX` line — beta is the
normal channel for OTel-Python contrib.) `python-json-logger` may be added for D4 if a custom
JSON formatter is cleaner than hand-rolling; decide at CODE, minimise deps.

## Files touched

### `mcp`
| File | Change |
|---|---|
| `pyproject.toml` | add the OTel deps above; add `[[tool.mypy.overrides]]` for `opentelemetry.instrumentation.*` (D6) |
| `src/rustok_mcp/telemetry.py` (new) | `init_telemetry(service_name) -> None`: validate endpoint, build TracerProvider + OTLP/HTTP BatchSpanProcessor (opt-in) + W3C propagator + `HTTPXClientInstrumentor().instrument()`; configure JSON logging + trace_id; no-op-OTLP path = JSON logs only |
| `src/rustok_mcp/main.py` | call `init_telemetry("rustok-mcp")` before app use; `FastAPIInstrumentor.instrument_app(app)` |
| `src/rustok_mcp/stdio.py` | call `init_telemetry("rustok-mcp")` (no FastAPI instrument) |
| `tests/` | endpoint validation (unset/valid/malformed); JSON log carries trace_id within a span; httpx inject smoke (a span is active → outgoing request carries `traceparent`) |

### `core` (gateway inbound extract)
| File | Change |
|---|---|
| `crates/gateway/src/otel_meta.rs` | add `HeaderExtractor`(`&http::HeaderMap`) + `extract_http_parent(&HeaderMap) -> opentelemetry::Context` |
| `crates/gateway/src/lib.rs` | in `TraceLayer::make_span_with`, `set_parent` from the extracted context before returning the span; unit test: known `traceparent` header → span adopts that trace_id |

### `meta`
| File | Change |
|---|---|
| `docker-compose.obs.yml` | add `mcp` override: `RUSTOK_OTLP_ENDPOINT=http://alloy:4318` + join `telemetry` network (mcp is on `edge`; alloy is on edge too, but join `telemetry` for parity/isolation) |
| `.env.example` / `README` | note mcp traces; full chain MCP→Gateway→Core |
| `docs/PROJECT-STATUS.md` | 5.2c done; e2e-trace gate met |

## Acceptance criteria

1. `ruff` clean, `mypy` clean, `pytest` green (existing + new); core gates stay green
   (`fmt`/`clippy`/`test`/`deny`).
2. **No-OTLP:** MCP with `RUSTOK_OTLP_ENDPOINT` unset → single-line JSON logs, no exporter, no
   network, no startup failure; SSE + stdio behave exactly as today.
3. **OTLP + full stack:** an MCP tool call (e.g. `get_wallet_context` over SSE) yields in Tempo
   **one trace** spanning `rustok-mcp` → `rustok-gateway` → `rustok-core`.
4. MCP JSON logs for that request carry the same `trace_id` (Loki ↔ Tempo).
5. Malformed `RUSTOK_OTLP_ENDPOINT` → fail fast at startup.
6. No regression: protocol/tool/auth behaviour unchanged; gateway behaviour for non-traced
   requests unchanged (root span as before).

## Test plan

1. **mcp unit:** endpoint validation; JSON formatter emits `trace_id` for a log inside a span +
   no ANSI; with `HTTPXClientInstrumentor` active, an outbound request under an active span
   carries a `traceparent` header (mock transport asserts the header).
2. **core unit:** `HeaderExtractor` round-trips a `traceparent`; `make_span_with` span adopts the
   header's trace_id (mirror the 5.2b link test).
3. **gates:** ruff/mypy/pytest (mcp); fmt/clippy/test/deny (core).
4. **live e2e (Docker, `sg docker`):** full stack base+obs (with a seeded keystore per the 5.2b
   procedure), drive an SSE tool call, verify criteria 3–4 in Tempo + Loki. (Re-uses the 5.2b
   e2e harness; keystore seeding + `RUSTOK_MCP_API_KEY` Bearer noted in memory.)

## Risks

- **R1 — OTel Python contrib beta churn (0.63bX).** API differs across betas. Verify
  `instrument_app` / `HTTPXClientInstrumentor` / exporter signatures at CODE; pin via `uv`.
- **R2 — Double server span.** `FastAPIInstrumentor` + any ASGI middleware could create nested
  spans; verify a single server span per request.
- **R3 — Endpoint `/v1/traces`** (same gotcha that cost 5.2b a debug cycle) — build the full URL
  explicitly; covered by criterion 3.
- **R4 — Gateway extract regression.** `set_parent`-before-enter is mandatory (5.2b); reuse that
  pattern. A bad `traceparent` must never break a Gateway request.
- **R5 — Cross-repo ordering.** mcp+core can merge before meta wiring (graceful degradation); e2e
  verified once all three are up.

## Definition of Done

- 3 PRs merged (mcp, core gateway-extract, meta wiring), branches deleted.
- Acceptance criteria demonstrated in the Gate-2 report (live e2e: full MCP→Gateway→Core trace).
- `docs/PROJECT-STATUS.md` (meta): 5.2c done; e2e-trace-in-Grafana gate met; 5.2d (metrics) next.
