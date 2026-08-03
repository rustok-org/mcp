#!/usr/bin/env bash
# Rustok self-custody wallet — Docker quick start.
# There is no binary to install: the wallet runs as one container over MCP stdio,
# with your keys in a local Docker volume. This script just prints the commands.
set -euo pipefail

IMAGE="${RUSTOK_WALLET_IMAGE:-ghcr.io/rustok-org/rustok-wallet:latest}"

cat <<EOF
Rustok self-custody wallet — quick start (Docker)

1) Pull the image:
   docker pull ${IMAGE}

2) Put the keyring password in a file the wallet reads — not in the command.
   Typed this way it never reaches your shell history, and it is in no
   process's environment inside the container:
   umask 077
   read -r -s -p "Keyring password: " pw
   printf '%s' "\$pw" > ~/.rustok-keyring-pass
   unset pw

3) Create your wallet once — back up the 12 words it prints:
   docker run -it --rm -v rustok-wallet:/data \\
     -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \\
     -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \\
     ${IMAGE} create-wallet

4) Run / connect an agent (MCP over stdio):
   docker run -i --rm -v rustok-wallet:/data \\
     -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \\
     -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \\
     -e RUSTOK_ALLOWED_CHAINS="1,8453" \\
     -e RUSTOK_RPC_URLS_1="https://your-rpc" \\
     ${IMAGE}

   Passing -e RUSTOK_KEYRING_PASSWORD=... still works, and the wallet clears it
   from every process it starts — but the runtime keeps a copy in the container
   config, where nothing inside the image can reach it. The file above avoids
   that copy entirely.

Claude Desktop / ClawHub / Smithery setup: see docs/INSTALL.md.
EOF
