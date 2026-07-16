# Installation

The Rustok wallet ships as **one self-contained Docker image**
(`ghcr.io/rustok-org/rustok-wallet-tui`) that runs Core + Gateway + MCP and speaks
MCP over **stdio**. It is **self-custody**: your keys live only in your local
Docker volume and never leave your machine.

## Prerequisites

- **Podman** (recommended — rootless, ships a secret store) or **Docker**, installed
  and running. Non-password commands below show `docker`; `podman` accepts the same
  syntax. Password delivery differs per engine — both variants are shown.
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for testing).

## 1. Pull the image

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1
```

## 2. Create your wallet (one time)

Run this in a **terminal the agent cannot see** (`docker run -it` attaches a real
TTY). It prints two things only once:

- the **12-word recovery phrase**;
- the **6-digit approval PIN** — keep it with the phrase; it unlocks the console
  session and is required for high-risk approvals.

**Podman (recommended)** — store the password once in podman's secret store: it never
touches shell history, `podman inspect` or the MCP config, and quotes in the password
are safe (they are read as-is, not parsed):

```bash
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" | podman secret create rustok-keyring-claude - && unset pw

podman run -it --rm \
  -v rustok-wallet-tui:/data \
  --secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1 create-wallet
```

**Docker** (no secret store without swarm) — keep the password in a `0600` file and
hand the wallet its *path* via `RUSTOK_KEYRING_PASSWORD_FILE` (a trailing newline in
the file is stripped):

```bash
umask 077
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" > ~/.rustok-keyring-pass && unset pw

docker run -it --rm \
  -v rustok-wallet-tui:/data \
  -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1 create-wallet
```

Back up the **12 words** and the **PIN** offline, then fund the address. If the
PIN is lost, open a shell in the running wallet container and reset it (see
[Opening the approval console](#opening-the-approval-console) for how to find the
container) — `… core-server set-pin` in place of `… rustok-console`.

## 3. Connect an agent (stdio)

The MCP client launches the image over stdio — **the password never goes into this
config file**. For **Claude Desktop / Cursor**, add to the MCP config
(`claude_desktop_config.json`); with podman the secret from step 2 does the delivery:

```json
{
  "mcpServers": {
    "rustok-wallet-tui": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "--init",
               "--label", "rustok=wallet", "--label", "rustok.agent=claude",
               "-v", "rustok-wallet-tui:/data",
               "--secret", "rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
               "ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1"]
    }
  }
}
```

With **docker**, swap the `--secret` argument pair for the `0600`-file mount from
step 2:

```jsonc
"command": "docker",
"args": ["run", "-i", "--rm", "--init",
         "--label", "rustok=wallet", "--label", "rustok.agent=claude",
         "-v", "rustok-wallet-tui:/data",
         "-v", "/home/you/.rustok-keyring-pass:/run/keyring-pass:ro",
         "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
         "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
         "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1"]
```

> **An RPC URL that embeds a provider key** (an Alchemy URL) is a credential too — on
> podman deliver it the same way: `--secret rustok-rpc-claude,type=env,target=RUSTOK_RPC_URLS_1`.
> The public-endpoint URLs above are not secrets.

> **Legacy: inline `-e` password / `--env-file`.** Older setups passed the password as
> `-e RUSTOK_KEYRING_PASSWORD=…` or via an env-file. Both still work but are
> deprecated: the value is visible in `inspect` (and, for the `env` block, in the MCP
> config file), and inside an env-file **quotes become part of the password** — a
> silent unlock failure that broke real onboardings. Migrate to the secret / `_FILE`
> delivery above.

For **ClawHub / Smithery**, install the `rustok-wallet-tui` skill and provide
`RUSTOK_KEYRING_PASSWORD` (and an RPC URL) when prompted; the registry flow passes it
as an env var — the secret/`_FILE` delivery above is the recommended manual setup.

> **Why labels, not `--name`.** The agent launches this container itself, and a
> fixed `--name` collides the moment anything starts a second instance (a health
> probe, a `claude mcp list`) — the launcher would refuse or, with `--replace`,
> kill your live wallet. The two `--label`s let the container run under an
> auto-generated name while staying discoverable; the `rustok.agent` sub-label
> identifies *which* agent's wallet it is (see below).

## Opening the approval console

The console is a **separate window** the agent cannot drive. The container has no
fixed name (see above), so find it by label:

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" rustok-console
```

This works while the agent session is live (the MCP client keeps the container
running). A short `rustok` command that wraps this discovery is coming; until
then, the one-liner above is the reliable way in. (Swap `rustok-console` for
`core-server set-pin` to reset a lost PIN.)

## Running a second agent

Each agent gets **its own wallet** — its own volume, keys and address. Sharing one
wallet between two agents is deliberately not supported yet: two independent
signers race the nonce and a decision can surface in the wrong console. Give the
second agent (e.g. Hermes) a distinct volume and sub-label:

```jsonc
"args": ["run", "-i", "--rm", "--init",
         "--label", "rustok=wallet", "--label", "rustok.agent=hermes",
         "-v", "rustok-hermes:/data",                // its own wallet volume
         "--secret", "rustok-keyring-hermes,type=env,target=RUSTOK_KEYRING_PASSWORD", …,
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1"]
```

`create-wallet` that volume once (as in step 2, with `-v rustok-hermes:/data` and its
own secret `rustok-keyring-hermes`), and open its console with
`--filter label=rustok.agent=hermes`.

## Upgrading the wallet image

Your wallet lives in the **volume**, not in the image — so upgrading is: pull the new
tag, recreate the container, keep the volume.

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1
# the agent-launched container is --rm (it disappears when the agent session ends);
# just restart the agent with the new tag in its MCP config, same -v … :/data volume
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
