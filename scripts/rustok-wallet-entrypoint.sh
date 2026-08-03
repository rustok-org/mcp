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

# The approver socket lives here, and so does a staged password (below).
# Recreate in case /run is a tmpfs (podman).
mkdir -p /run/wallet

# ─── The keyring password reaches core as a FILE, and only as a file ──────────
#
# It used to reach it as an environment variable, which meant every process in
# the container — core, the gateway, the MCP server — carried it in
# /proc/<pid>/environ, readable by anything running as the same user. Only core
# needs the password at all; the other two held it purely because they inherited
# it from here.
#
# So: whatever way the password arrives, it leaves this block as a *path*, and
# the value is never exported. `STAGED_PASSWORD_FILE` is non-empty only when we
# wrote the file ourselves, which is also the only file we are allowed to delete.
STAGED_PASSWORD_FILE=""
PASSWORD_FILE=""
cleanup_staged_password() {
    if [ -n "$STAGED_PASSWORD_FILE" ]; then
        rm -f "$STAGED_PASSWORD_FILE"
        STAGED_PASSWORD_FILE=""
    fi
}

if [ -n "${RUSTOK_KEYRING_PASSWORD:-}" ]; then
    # Compatibility path: the password arrived as a plain value. Stage it in a
    # file only this user can read, then drop the variable so that nothing
    # started from here inherits it. What cannot be undone from inside the
    # container is the copy the runtime keeps in the container config
    # (`podman inspect`) and, under `--init`, in its own PID 1 — which is why
    # the file delivery below is the documented one.
    STAGED_PASSWORD_FILE=/run/wallet/keyring-password
    ( umask 077; printf '%s' "$RUSTOK_KEYRING_PASSWORD" >"$STAGED_PASSWORD_FILE" )
    unset RUSTOK_KEYRING_PASSWORD
    PASSWORD_FILE="$STAGED_PASSWORD_FILE"
elif [ -n "${RUSTOK_KEYRING_PASSWORD_FILE:-}" ]; then
    # A file the operator mounted (`podman secret …,type=mount`, or a docker
    # bind-mount) via the standard _FILE convention. It belongs to them: it is
    # read here only to fail fast and by name, and never deleted.
    #
    # Two guards, one named error. `[ -f ]` is a stat(2) check that rejects
    # what would hang the read forever (a FIFO, a device, a directory) — and it
    # is NOT `test -r`: under SELinux (podman on Fedora, a bind-mount without
    # `:z`) access(2) says yes while open(2) is denied, so the read itself
    # stays guarded too and fails as the same named error.
    if [ ! -f "$RUSTOK_KEYRING_PASSWORD_FILE" ] \
        || ! probe="$(cat "$RUSTOK_KEYRING_PASSWORD_FILE" 2>/dev/null)"; then
        echo "rustok-wallet-tui: RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file: $RUSTOK_KEYRING_PASSWORD_FILE" 1>&2
        exit 1
    fi
    # `$(…)` strips trailing newlines, so this rejects exactly what core would
    # read as no password at all — a file holding only a line ending included.
    if [ -z "$probe" ]; then
        echo "rustok-wallet-tui: RUSTOK_KEYRING_PASSWORD_FILE is empty: $RUSTOK_KEYRING_PASSWORD_FILE" 1>&2
        exit 1
    fi
    probe=""
    PASSWORD_FILE="$RUSTOK_KEYRING_PASSWORD_FILE"
fi
# Neither set: say nothing here and let core name what it needs. Its message
# lists both ways of supplying the password; a second one from here would only
# compete with it.

# From here on every exit removes a staged copy — including the failure paths
# further down. A container whose core never came up would otherwise keep the
# password in its filesystem for as long as the stopped container is kept
# around, and `podman cp` reaches it there. Measured, not assumed: without this
# the file was still in the exited container's layer.
trap cleanup_staged_password EXIT INT TERM

if [ "$1" = "create-wallet" ]; then
    # `exec`, for the same reason the serving path ends in one: `/proc/1/environ`
    # is the environment this process was *started* with, so the `unset` above
    # did not reach it, and onboarding — argon2 over a fresh keystore — is long
    # enough to be worth reading. The replacement is a shell rather than
    # core-server itself because the staged file still has to go afterwards, and
    # a trap does not survive `exec`.
    exec sh -c '
        RUSTOK_KEYRING_PASSWORD_FILE="$1" core-server create-wallet
        status=$?
        [ -z "$2" ] || rm -f "$2"
        exit $status
    ' rustok-wallet-entrypoint "$PASSWORD_FILE" "$STAGED_PASSWORD_FILE"
fi

# Backend in the background; stdout -> stderr so it never pollutes the MCP channel.
# Core MUST be up before the Gateway starts — the Gateway connects to Core once
# at startup, so a race leaves it with no Core client (/health never serving).

# 1. Core (gRPC) first. It is the only process that gets the password's path —
#    the gateway and the MCP server never read it, and now no longer hold it.
RUSTOK_GRPC_ADDR="127.0.0.1:50051" RUSTOK_KEYRING_PASSWORD_FILE="$PASSWORD_FILE" core-server 1>&2 &

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

# Core is serving, which means it has already read the password — a staged copy
# has done its job and is removed here, so the settled container holds the secret
# in no environment and in no file of ours. A file the operator mounted is left
# exactly where they put it.
cleanup_staged_password

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
#
# `exec tini`, not a bare exec: this shell has been PID 1 since the container
# started, and PID 1 must reap the zombies that core and the gateway leave
# behind. Handing the role over through `exec` — rather than starting under tini
# — is also what clears the compatibility path's last carrier: /proc/1/environ
# is the environment a process was *started* with, so `unset` above never
# reached it, and only replacing the process image rewrites that region.
RUSTOK_MCP_GATEWAY_URL="http://127.0.0.1:3000" exec tini -- rustok-mcp-stdio
