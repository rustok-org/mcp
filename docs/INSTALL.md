# Installation

The Rustok wallet ships as **one self-contained Docker image**
(`ghcr.io/rustok-org/rustok-wallet-tui`) that runs Core + Gateway + MCP and speaks
MCP over **stdio**. It is **self-custody**: your keys live only in your local
Docker volume and never leave your machine.

## Prerequisites

- **Docker** installed and running.
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for testing).

## 1. Pull the image

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.6.0
```

## 2. Create your wallet (one time)

Run this in a **terminal the agent cannot see** (`docker run -it` attaches a real
TTY). It prints two things only once:

- the **12-word recovery phrase**;
- the **6-digit approval PIN** — keep it with the phrase; it unlocks the console
  session and is required for high-risk approvals.

```bash
docker run -it --rm --name rustok-wallet-tui \
  -v rustok-wallet-tui:/data \
  -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.6.0 create-wallet
```

Back up the **12 words** and the **PIN** offline, then fund the address. If the
PIN is lost, run `docker exec -it rustok-wallet-tui core-server set-pin`.

## 3. Connect an agent (stdio)

The MCP client launches the image over stdio. For **Claude Desktop / Cursor**, add
to the MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rustok-wallet-tui": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init", "--name", "rustok-wallet-tui",
               "-v", "rustok-wallet-tui:/data",
               "-e", "RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet-tui:v0.6.0"],
      "env": {
        "RUSTOK_KEYRING_PASSWORD": "your-strong-password",
        "RUSTOK_RPC_URLS_1": "https://ethereum-rpc.publicnode.com"
      }
    }
  }
}
```

For **ClawHub / Smithery**, install the `rustok-wallet-tui` skill and provide
`RUSTOK_KEYRING_PASSWORD` (and an RPC URL) when prompted; the registry runs the
same `docker run -i` command.

## Upgrading the wallet image

Your wallet lives in the **volume**, not in the image — so upgrading is: pull the new
tag, recreate the container, keep the volume.

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.6.0
docker rm -f rustok-wallet-tui            # the old container; the volume is untouched
# then start the new image with the SAME -v rustok-wallet-tui:/data as before
```

- **Your keys, address and PIN survive.** They are in the volume
  (`rustok-wallet-tui:/data`). Do **not** run `create-wallet` again — the wallet is
  already there, and the command refuses to overwrite an existing keystore anyway.
- **Point the new container at the same volume.** A different `-v` name is a different
  (empty) wallet, not an upgraded one.
- **Update the image tag in your agent's MCP config too** — the agent spawns the
  container itself, so a stale tag there keeps running the old wallet.
- **Anything waiting for approval is lost.** The pending queue lives in the running
  container's memory, so a transaction the agent parked but you never approved does not
  survive the restart. Nothing is signed or sent — the agent simply has to propose it
  again. Approve or deny what is open **before** you upgrade.
- Coming from the **agent edition** (`rustok-wallet`)? That is a different product with
  its own volume and its own keys — there is no in-place migration: create a wallet in
  the console edition and move the funds on-chain.

## Next steps

- [Configuration](CONFIGURATION.md) — chains, RPC, vaults, capabilities.
- [Troubleshooting](TROUBLESHOOTING.md) — common issues.
