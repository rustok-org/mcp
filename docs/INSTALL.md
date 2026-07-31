# Installation

The Rustok wallet ships as **one self-contained Docker image**
(`ghcr.io/rustok-org/rustok-wallet`) that runs Core + Gateway + MCP and speaks
MCP over **stdio**. It is **self-custody**: your keys live only in your local
Docker volume and never leave your machine.

## Prerequisites

- **Docker** or **Podman** installed and running (the commands below show both;
  podman users get the secret-store path, docker users the `_FILE` path).
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for testing).

## 1. Pull the image

```bash
docker pull ghcr.io/rustok-org/rustok-wallet:latest   # or: podman pull …
```

## 2. Create your wallet (one time)

The keyring password must **never** appear in your shell history, in the MCP
config, or in `docker/podman inspect`. Deliver it as a secret:

**Podman** — via the secret store (`read -s` keeps it out of history; the
`type=env` secret injects it byte-exact and `podman inspect` never shows it):

```bash
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" | podman secret create rustok-keyring - && unset pw

podman run -it --rm \
  -v rustok-wallet:/data \
  --secret rustok-keyring,type=env,target=RUSTOK_KEYRING_PASSWORD \
  ghcr.io/rustok-org/rustok-wallet:latest create-wallet
```

**Docker** (no secret store without swarm) — keep the password in a `0600` file
and hand the wallet its *path* via `RUSTOK_KEYRING_PASSWORD_FILE` (a trailing
newline in the file is stripped):

```bash
umask 077
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" > ~/.rustok-keyring-pass && unset pw

docker run -it --rm \
  -v rustok-wallet:/data \
  -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \
  ghcr.io/rustok-org/rustok-wallet:latest create-wallet
```

Run this in a terminal and **write down the 24-word recovery phrase** — it is
shown only once. It prints your wallet **address** and the **24 words**. Back
them up offline, then fund the address. (Recovery = the 24 words, importable
into any standard wallet, or the `rustok-wallet` volume + your password.)

> **Headless/CI:** replace `-it` with `-i`. The password is already supplied
> via the secret / `_FILE`, so no TTY is required.

## 3. Connect an agent (stdio)

The MCP client launches the image over stdio — **the password never goes into
this config file**. For **Claude Desktop / Cursor**, add to the MCP config
(`claude_desktop_config.json`).

**Podman** (the secret from step 2 does the delivery):

```json
{
  "mcpServers": {
    "rustok-wallet": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "--init",
               "-v", "rustok-wallet:/data",
               "--secret", "rustok-keyring,type=env,target=RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet:latest"],
      "env": {
        "RUSTOK_RPC_URLS_1": "https://ethereum-rpc.publicnode.com"
      }
    }
  }
}
```

**Docker** — replace the `--secret` arg with the bind-mount pair (use your real
absolute path; `~` is not expanded inside JSON):

```json
               "-v", "/home/you/.rustok-keyring-pass:/run/keyring-pass:ro",
               "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
```

For **ClawHub / Smithery**, install the `rustok-wallet` skill; it walks you
through the same secret / `_FILE` setup for your engine.

> **An RPC URL that embeds a provider key** (an Alchemy URL) is a credential
> too — on podman deliver it the same way:
> `--secret rustok-rpc,type=env,target=RUSTOK_RPC_URLS_1` (and drop it from the
> `env` block). The public-endpoint URLs above are not secrets.

## Next steps

- [Configuration](CONFIGURATION.md) — chains, RPC, vaults, capabilities.
- [Troubleshooting](TROUBLESHOOTING.md) — common issues.
