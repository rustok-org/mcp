# syntax=docker/dockerfile:1
# Multi-stage build for the rustok-mcp Python server.
#
# Build:
#   docker build -t rustok-mcp:v0.1.0 .
# Run (SSE transport):
#   docker run -p 127.0.0.1:3001:3001 -e RUSTOK_MCP_HOST=0.0.0.0 rustok-mcp:v0.1.0

# ------------------------------------------------------------------
# Stage 1 — Builder (uv resolves and installs the locked environment)
# ------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first for caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Project layer.
COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------------
# Stage 2 — Runtime
# ------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with fixed UID/GID (matches docker-compose).
RUN groupadd -g 1000 rustok && useradd -u 1000 -g rustok -m rustok

COPY --from=builder --chown=rustok:rustok /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER rustok
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3001/health', timeout=2)"]

# SSE transport by default; use `rustok-mcp-stdio` for stdio transport.
ENTRYPOINT ["rustok-mcp"]
