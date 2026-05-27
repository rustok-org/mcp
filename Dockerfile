FROM rust:1.85-slim-bookworm AS builder
WORKDIR /app
COPY . .
RUN cargo build --release --bin rustok-mcp

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/rustok-mcp /usr/local/bin/rustok-mcp
RUN useradd -m -u 1000 rustok
USER rustok
VOLUME ["/data"]
ENV DATA_DIR=/data
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:3000/health || exit 1
ENTRYPOINT ["rustok-mcp"]
CMD ["--host", "0.0.0.0", "--port", "3000"]
