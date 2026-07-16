#!/bin/sh
# Entrypoint for the all-in-one self-custody wallet image.
#
# Default: start Core (gRPC) + Gateway (HTTP) in the background on loopback, wait
# for them to be ready, then hand the container's stdin/stdout to the MCP stdio
# server. The MCP JSON-RPC channel is stdout — so ALL backend logs go to stderr.
#
# `create-wallet`: one-shot onboarding — create the keystore and print the 12-word
# recovery phrase + approval PIN on the TTY (`docker run -it ... create-wallet`),
# then exit.
set -e

: "${RUSTOK_DATA_DIR:=/data}"
export RUSTOK_DATA_DIR

# The keyring password may arrive as a FILE (`podman secret …,type=mount`, or a
# docker bind-mount) via the standard _FILE convention. An explicit
# RUSTOK_KEYRING_PASSWORD always wins — then the file is not even looked at.
# $(cat …) strips trailing newlines, same as the official-image `_FILE` readers.
if [ -z "${RUSTOK_KEYRING_PASSWORD:-}" ] && [ -n "${RUSTOK_KEYRING_PASSWORD_FILE:-}" ]; then
    # Two guards, one named error. `[ -f ]` is a stat(2) check that rejects
    # what would hang `cat` forever (a FIFO, a device, a directory) — and it is
    # NOT `test -r`: under SELinux (podman on Fedora, a bind-mount without
    # `:z`) access(2) says yes while open(2) is denied, so the read itself
    # stays guarded too and fails as the same named error, never a raw `cat`.
    if [ ! -f "$RUSTOK_KEYRING_PASSWORD_FILE" ] \
        || ! RUSTOK_KEYRING_PASSWORD="$(cat "$RUSTOK_KEYRING_PASSWORD_FILE" 2>/dev/null)"; then
        echo "rustok-wallet-tui: RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file: $RUSTOK_KEYRING_PASSWORD_FILE" 1>&2
        exit 1
    fi
    if [ -z "$RUSTOK_KEYRING_PASSWORD" ]; then
        echo "rustok-wallet-tui: RUSTOK_KEYRING_PASSWORD_FILE is empty: $RUSTOK_KEYRING_PASSWORD_FILE" 1>&2
        exit 1
    fi
    export RUSTOK_KEYRING_PASSWORD
fi

# The approver socket lives here. Recreate in case /run is a tmpfs (podman).
mkdir -p /run/wallet

if [ "$1" = "create-wallet" ]; then
    exec core-server create-wallet
fi

# Backend in the background; stdout -> stderr so it never pollutes the MCP channel.
# Core MUST be up before the Gateway starts — the Gateway connects to Core once
# at startup, so a race leaves it with no Core client (/health never serving).

# 1. Core (gRPC) first.
RUSTOK_GRPC_ADDR="127.0.0.1:50051" core-server 1>&2 &

# 2. Wait for Core's gRPC port to accept connections, then start the Gateway.
i=0
while ! python -c "import socket,sys; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',50051)); s.close(); sys.exit(0 if r==0 else 1)" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
        echo "rustok-wallet-tui: core (gRPC) not ready after 60s — is RUSTOK_KEYRING_PASSWORD set and a wallet created (run 'create-wallet' first)?" 1>&2
        exit 1
    fi
    sleep 1
done

# Authenticate the loopback gateway<->mcp hop without user config. Respect an
# explicit user key or explicit dev mode; otherwise mint an ephemeral one.
if [ -z "${RUSTOK_MCP_API_KEY:-}" ] && [ "${RUSTOK_GATEWAY_DEV:-}" != "1" ]; then
    RUSTOK_MCP_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export RUSTOK_MCP_API_KEY

RUSTOK_GATEWAY_ADDR="127.0.0.1:3000" RUSTOK_CORE_ADDR="http://127.0.0.1:50051" gateway 1>&2 &

# 3. Wait until the gateway reports the core serving.
i=0
while ! python -c "import urllib.request,sys; sys.exit(0 if b'\"core\":\"serving\"' in urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=2).read() else 1)" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -gt 30 ]; then
        echo "rustok-wallet-tui: gateway not ready after 30s" 1>&2
        exit 1
    fi
    sleep 1
done

# stdin/stdout become the MCP JSON-RPC channel; talks to the local gateway.
RUSTOK_MCP_GATEWAY_URL="http://127.0.0.1:3000" exec rustok-mcp-stdio
