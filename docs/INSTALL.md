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
docker pull ghcr.io/rustok-org/rustok-wallet:latest
```

## 2. Create your wallet (one time)

Run this in a terminal and **write down the 24-word recovery phrase** — it is
shown only once:

```bash
docker run -it --rm \
  -v rustok-wallet:/data \
  -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \
  ghcr.io/rustok-org/rustok-wallet:latest create-wallet
```

It prints your wallet **address** and the **24 words**. Back them up offline,
then fund the address. (Recovery = the 24 words, importable into any standard
wallet, or the `rustok-wallet` volume + your password.)

## 3. Connect an agent (stdio)

The MCP client launches the image over stdio. For **Claude Desktop / Cursor**, add
to the MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rustok-wallet": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init",
               "-v", "rustok-wallet:/data",
               "-e", "RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet:latest"],
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
