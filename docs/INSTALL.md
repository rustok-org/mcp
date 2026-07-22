# Installation

The Rustok wallet is **one self-contained container image**
(`ghcr.io/rustok-org/rustok-wallet-tui`) that runs Core + Gateway + MCP and speaks
MCP over **stdio**, driven by a small `rustok` command on your machine. It is
**self-custody**: your keys live only in a local container volume and never leave
it.

One command installs it; `rustok` does the rest.

## Prerequisites

- **Podman** (recommended — rootless, ships a secret store) or **Docker**.
- **curl**.
- **cosign — optional.** It is a *provenance* tool: it proves the image was
  built by this repository's workflow. It is **not** what makes the download
  trustworthy — the installer pulls **by digest**, so you get exactly the bytes
  pinned in the script or nothing at all. If cosign is present and working the
  installer verifies the signature; if it is missing (or installed but unable to
  run) the installer says so, skips that check and continues. A signature that
  is present but *does not verify* still stops the install.
  [installation](https://docs.sigstore.dev/cosign/installation) — nothing else
  in the wallet uses it.
- **`jq`** — needed only by `rustok connect claude` / `connect cursor`;
  **`python3` + PyYAML** — needed only by `rustok connect hermes`.
  `rustok doctor` tells you which of these you are missing.
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for
  testing).

**Platforms.** The published image is `linux/amd64`, and the installer is POSIX
`sh`. Linux is the tested path. On **Windows, install inside WSL2** and treat it
as a Linux machine — there is no native Windows installer, and we are not going
to pretend otherwise. macOS and `arm64` are not published yet.

## 1. Install

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.8.1/scripts/install.sh | sh
```

### Inspect it before you run it

This is a wallet — reading the script first is a reasonable thing to want. Fetch
it to a file, read that file, then run **that same file**: what you read is
exactly what runs.

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.8.1/scripts/install.sh -o install.sh
less install.sh      # ~150 lines of POSIX sh
sh install.sh
```

The release notes for that tag publish the script's `sha256` if you prefer to
check the bytes instead of reading them.

> **What the tag in that URL is and is not.** It pins a *version* — it is not a
> cryptographic identity. A git tag can in principle be repointed at a different
> commit, so treat the tag as "which release", not as proof of content. The
> identities that are bound to exact bytes are the ones **inside** the script:
> the image `@sha256:` digest it pulls and the commit SHA it fetches the shim
> from. For the script itself, the published `sha256` is the check.

### What the installer does — and what it deliberately does not

1. **Checks provenance first, when it can.** If cosign is available and runnable
   it verifies the image's signature against this repository's publishing
   workflow *before* anything is written to disk — a wrong-identity image is
   refused, not downloaded. If cosign is missing or cannot run, the installer
   prints that plainly and carries on: provenance is a layer on top, not the
   thing that keeps you safe. What it will never do is fail *quietly* — a cosign
   that runs and disagrees aborts the install.
2. Pulls the image **by digest** (`@sha256:…`), so a mutable tag cannot be
   repointed at different bytes underneath you. This — not cosign — is what
   guarantees you get the exact image this release pinned.
3. Fetches the `rustok` shim from a **commit-pinned** URL over
   `--proto '=https' --tlsv1.2` and installs it to `~/.local/bin`.
4. Adds `~/.local/bin` to your `PATH` in one marked block of your shell profile.
   Set `RUSTOK_NO_MODIFY_PATH=1` to skip that and get the line to add yourself.

It **never touches a secret, a keystore volume or your wallet.** Creating the
wallet — the part that prints your recovery phrase — is a separate step *you*
run in your own terminal. A recovery phrase must never travel through a pipe.

If `rustok` is not found afterwards, open a new shell (or `. ~/.bashrc`), then
run `rustok doctor`.

## 2. Create your wallet — `rustok init`

Run this in a **terminal the agent cannot see**. It prints two things exactly
once:

- the **12-word recovery phrase**;
- the **6-digit approval PIN** — keep it with the phrase; it unlocks the console
  session and is required for high-risk approvals.

```bash
rustok init
```

It asks for a keyring password twice, stores it where the engine keeps secrets
(podman's secret store, or a `0600` file in your config dir — `~/.config/rustok`
by default — on docker), then creates the wallet. The password never reaches your
shell history, `inspect`, or any agent config file.

`rustok init` **refuses to run without a real terminal of your own**: through a
pipe or an agent shell it stops with a named error rather than printing a
recovery phrase into somewhere it should never appear.

Back up the **12 words** and the **PIN** offline, then fund the printed address.

`init` creates **new** wallets and never touches an existing keystore: if the
wallet is already there it refuses. To re-store a changed keyring password
without touching the keys, use `rustok init --force`.

## 3. Connect your agent — `rustok connect`

```bash
rustok connect claude     # writes ~/.claude.json
rustok connect cursor     # writes ~/.cursor/mcp.json
rustok connect hermes     # writes ~/.hermes/config.yaml
```

This registers the wallet as an MCP server for that client, launching it by
label (never by a fixed `--name` — see below) with the password delivered
through the secret store. Add `--force` to replace an existing registration; the
old entry is printed first.

Each client gets **its own wallet** by default (its own volume, keys and
address) — see [Running a second agent](#running-a-second-agent).

**Keyed RPC URLs are credentials too.** Export the RPC URL before connecting and
the shim stores it as a per-agent secret, so it stays out of argv, out of the
agent's config file and out of `inspect`:

```bash
export RUSTOK_RPC_URLS_1="https://eth-mainnet.g.alchemy.com/v2/<your-key>"
rustok connect claude
```

Restart the client afterwards so it picks up the new MCP server.

## 4. Approve transactions — `rustok console`

The console is a **separate window the agent cannot drive**. Transactions that
move funds are parked by the wallet until you release them here:

```bash
rustok console      # also the default: bare `rustok` does the same
```

If the wallet is not running yet but is initialized, the console starts it and
attaches. If several wallets are running, it names them and asks which one:

```
rustok: multiple wallets running: claude, hermes — use --agent <name>
```

## Day to day

```bash
rustok status       # which wallets are running, under which image
rustok doctor       # engine, PATH, jq/PyYAML, running wallets, leftovers
rustok start        # start this agent's wallet in the background
rustok stop         # stop it
```

`rustok doctor` is the first thing to run when something looks wrong — it checks
the engine is actually responding, that `~/.local/bin` is on your `PATH`, and
that the optional tools `connect` needs are present.

## Updating

```bash
rustok update
```

Pulls the current wallet image and re-registers every rustok MCP entry it finds
across claude / cursor / hermes, each keeping its own wallet. A failed pull stops
the run before any config is touched. Wallets that are running keep the previous
image until their agent's next session starts (or until `rustok stop`).

> **What `update` does not do.** `rustok update` **pulls by tag** and, unlike the
> installer, **does not re-run the cosign verification** of the image. The
> signature guarantee you get from `install.sh` covers *installation*, not the
> whole lifecycle. Re-running the installer for a new release gives you the
> verified path again.

**The shim does not update itself** — re-run the installer to get a newer
`rustok`. To move to a different version (including going back to an older one),
run the installer from that version's tag: the URL above is a normal repository
tag, so replacing it with the version you want is all it takes.

Your keys, address and PIN live in the **volume**, not in the image, so they
survive every update. Anything waiting for approval does not: the pending queue
lives in the running container's memory, so approve or deny what is open
**before** you update. Nothing is signed or sent — the agent simply has to
propose it again.

## Uninstalling

```bash
rustok uninstall
```

Data-safe teardown, the install in reverse: deregisters from every agent, stops
running wallets, removes the stored passwords/RPC secrets, removes the
installer's `PATH` block and the shim itself. **Your keystore volumes are never
touched** — it prints their names and leaves them.

To delete the keys as well:

```bash
rustok uninstall --purge-keys
```

This lists every volume it is about to delete, then requires you to type
`delete my keys` on your own terminal. It refuses to run through a pipe or an
agent. **Without your seed-phrase backup, the funds are unrecoverable.**

## Running a second agent

Each agent gets **its own wallet** — its own volume, keys and address. Sharing
one wallet between two agents is deliberately not supported: two independent
signers race the nonce and a decision can surface in the wrong console.

```bash
rustok init --agent hermes        # its own keystore volume + password
rustok connect hermes
rustok console --agent hermes     # its own approval window
```

`--agent` names whose wallet you mean; `claude` is the default and keeps the
historical volume name (`rustok-wallet-tui`), any other agent gets
`rustok-<name>`.

> **Why labels, not `--name`.** The agent launches this container itself, and a
> fixed `--name` collides the moment anything starts a second instance (a health
> probe, an `mcp list`) — the launcher would refuse or, with `--replace`, kill
> your live wallet. The wallet runs with `--label rustok=wallet` plus a
> `rustok.agent=<name>` sub-label instead: an auto-generated container name, but
> still discoverable, and the sub-label says *which* agent's wallet it is.

## Appendix: installing without the shim

Everything above is optional convenience. If you would rather not pipe a script
into a shell, or you want to see exactly what the shim writes, this is the same
setup by hand. It is also the reference for what a registration looks like.

### Create the wallet

**Podman (recommended)** — store the password once in podman's secret store: it
never touches shell history, `podman inspect` or the MCP config, and quotes in
the password are safe (they are read as-is, not parsed):

```bash
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" | podman secret create rustok-keyring-claude - && unset pw

podman run -it --rm \
  -v rustok-wallet-tui:/data \
  --secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0 create-wallet
```

**Docker** (no secret store without swarm) — keep the password in a `0600` file
and hand the wallet its *path* via `RUSTOK_KEYRING_PASSWORD_FILE` (a trailing
newline in the file is stripped). The path below is yours to choose; the shim
keeps its own at `~/.config/rustok/keyring-pass-<agent>`:

```bash
umask 077
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" > ~/.rustok-keyring-pass && unset pw

docker run -it --rm \
  -v rustok-wallet-tui:/data \
  -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0 create-wallet
```

Either way, `create-wallet` prints the **12-word recovery phrase** and the
**6-digit approval PIN** exactly once. Back both up offline before going further,
then fund the printed address — nothing later in this appendix will show them
again.

### Register it with an agent

The MCP client launches the image over stdio — **the password never goes into
this config file**. With podman the secret above does the delivery:

```json
{
  "mcpServers": {
    "rustok": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "--init",
               "--label", "rustok=wallet", "--label", "rustok.agent=claude",
               "-v", "rustok-wallet-tui:/data",
               "--secret", "rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
               "ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"]
    }
  }
}
```

With **docker**, swap the `--secret` argument pair for the `0600`-file mount:

```jsonc
"command": "docker",
"args": ["run", "-i", "--rm", "--init",
         "--label", "rustok=wallet", "--label", "rustok.agent=claude",
         "-v", "rustok-wallet-tui:/data",
         "-v", "/home/you/.rustok-keyring-pass:/run/keyring-pass:ro",
         "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
         "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
         "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"]
```

> **An RPC URL that embeds a provider key** (an Alchemy URL) is a credential too
> — on podman deliver it the same way:
> `--secret rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1`.
> The public-endpoint URLs above are not secrets.

> **Legacy: inline `-e` password / `--env-file`.** Older setups passed the
> password as an inline `-e` value, forwarded it from the caller's environment,
> or used an env-file. All still work and all are deprecated: the value is
> visible in `inspect` (and, for an env block, in the MCP config file), and
> inside an env-file **quotes become part of the password** — a silent unlock
> failure that broke real onboardings. Use the secret / `_FILE` delivery above.

### Open the console by label

The container has no fixed name, so find it by label:

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" rustok-console
```

(Swap `rustok-console` for `core-server set-pin` to reset a lost PIN — this needs
the keyring password and an interactive TTY.)

### A second agent, by hand

Give it a distinct volume and sub-label, and its own secret:

```jsonc
"args": ["run", "-i", "--rm", "--init",
         "--label", "rustok=wallet", "--label", "rustok.agent=hermes",
         "-v", "rustok-hermes:/data",                // its own wallet volume
         "--secret", "rustok-keyring-hermes,type=env,target=RUSTOK_KEYRING_PASSWORD", …,
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"]
```

`create-wallet` that volume once (as above, with `-v rustok-hermes:/data` and its
own secret), and open its console with `--filter label=rustok.agent=hermes`.

### Upgrading by hand

Pull the new tag, restart the agent, keep the volume:

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0
# the agent-launched container is --rm (it disappears when the agent session ends);
# just restart the agent with the new tag in its MCP config, same -v … :/data volume
```

- **Point the new container at the same volume.** A different `-v` name is a
  different (empty) wallet, not an upgraded one.
- **Update the image tag in your agent's MCP config too** — the agent spawns the
  container itself, so a stale tag there keeps running the old wallet.
- Coming from the **agent edition** (`rustok-wallet`)? That is a different
  product with its own volume and its own keys — there is no in-place migration:
  create a wallet in the console edition and move the funds on-chain.

## Next steps

- [Configuration](CONFIGURATION.md) — chains, RPC, vaults, capabilities.
- [Troubleshooting](TROUBLESHOOTING.md) — common issues.
