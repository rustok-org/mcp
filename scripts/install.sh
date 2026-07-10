#!/usr/bin/env bash
# Rustok self-custody wallet — Docker quick start.
# There is no binary to install: the wallet runs as one container over MCP stdio,
# with your keys in a local Docker volume. This script just prints the commands.
set -euo pipefail

IMAGE="${RUSTOK_WALLET_IMAGE:-ghcr.io/rustok-org/rustok-wallet-tui:v0.5.0}"

cat <<EOF
Rustok self-custody wallet — quick start (Docker)

1) Pull the image:
   docker pull ${IMAGE}

2) Create your wallet once — back up the 12 words and approval PIN it prints:
   docker run -it --rm --name rustok-wallet-tui -v rustok-wallet-tui:/data \\
     -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \\
     ${IMAGE} create-wallet

3) Run / connect an agent (MCP over stdio):
   docker run -i --rm --init --name rustok-wallet-tui -v rustok-wallet-tui:/data \\
     -e RUSTOK_KEYRING_PASSWORD="..." \\
     -e RUSTOK_ALLOWED_CHAINS="1,8453" \\
     -e RUSTOK_RPC_URLS_1="https://your-rpc" \\
     ${IMAGE}

Approve transactions in a separate terminal:
   docker exec -it rustok-wallet-tui rustok-console

Claude Desktop / ClawHub / Smithery setup: see docs/INSTALL.md.
EOF
