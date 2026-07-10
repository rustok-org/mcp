# Installation

The Rustok wallet ships as **one self-contained Docker image**
(`ghcr.io/rustok-org/rustok-wallet`) that runs Core + Gateway + MCP and speaks
MCP over **stdio**. It is **self-custody**: your keys live only in your local
Docker volume and never leave your machine.

## Prerequisites

- **Docker** installed and running.
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for testing).

## 1. Pull the image

```bash
docker pull ghcr.io/rustok-org/rustok-wallet:v0.5.0
```

## 2. Create your wallet (one time)

Run this in a **terminal the agent cannot see** (`docker run -it` attaches a real
TTY). It prints two things only once:

- the **12-word recovery phrase**;
- the **6-digit approval PIN** — keep it with the phrase; it unlocks the console
  session and is required for high-risk approvals.

```bash
docker run -it --rm --name rustok-wallet \
  -v rustok-wallet:/data \
  -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \
  ghcr.io/rustok-org/rustok-wallet:v0.5.0 create-wallet
```

Back up the **12 words** and the **PIN** offline, then fund the address. If the
PIN is lost, run `docker exec -it rustok-wallet core-server set-pin`.

## 3. Connect an agent (stdio)

The MCP client launches the image over stdio. For **Claude Desktop / Cursor**, add
to the MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rustok-wallet": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init", "--name", "rustok-wallet",
               "-v", "rustok-wallet:/data",
               "-e", "RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet:v0.5.0"],
      "env": {
        "RUSTOK_KEYRING_PASSWORD": "your-strong-password",
        "RUSTOK_RPC_URLS_1": "https://ethereum-rpc.publicnode.com"
      }
    }
  }
}
```

For **ClawHub / Smithery**, install the `rustok-wallet` skill and provide
`RUSTOK_KEYRING_PASSWORD` (and an RPC URL) when prompted; the registry runs the
same `docker run -i` command.

## Next steps

- [Configuration](CONFIGURATION.md) — chains, RPC, vaults, capabilities.
- [Troubleshooting](TROUBLESHOOTING.md) — common issues.
