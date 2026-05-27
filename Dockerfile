# syntax=docker/dockerfile:1
# Multi-stage build for rustok-agent-mcp distribution image.
# The binary is expected to be present in the build context (downloaded by CI).

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates=20230311 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -r rustok && useradd -r -g rustok -m rustok

# Pre-create data directory so named volumes inherit correct ownership
RUN mkdir -p /home/rustok/.rustok/agent && chown -R rustok:rustok /home/rustok/.rustok

# Copy prebuilt binary from build context
ARG BINARY_PATH=rustok-agent-mcp
COPY --chown=rustok:rustok ${BINARY_PATH} /usr/local/bin/rustok-agent-mcp
RUN chmod +x /usr/local/bin/rustok-agent-mcp

USER rustok
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD bash -c 'printf "GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n" > /dev/tcp/localhost/3000' || exit 1

ENTRYPOINT ["/usr/local/bin/rustok-agent-mcp"]
CMD ["--host", "0.0.0.0", "--port", "3000"]
