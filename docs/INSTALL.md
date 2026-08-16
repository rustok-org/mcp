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
  is present but *does not verify* still stops the install. If you do install
  it, use **cosign 3 or newer**: our signatures are stored as OCI referrers, and
  cosign 2.x cannot see them at all — it reports `no signatures found`, which
  the installer must treat as a refusal.
  [installation](https://docs.sigstore.dev/cosign/installation) — nothing else
  in the wallet uses it.
- **`jq`** — needed only by `rustok connect claude` / `connect cursor` /
  `connect openclaw`; **`python3` + PyYAML** — needed only by
  `rustok connect hermes`; the **`openclaw`** CLI — needed only by
  `rustok connect openclaw`, which registers through it.
  `rustok doctor` tells you which of these you are missing.
- An Ethereum RPC URL (an Alchemy key URL is recommended; a public RPC works for
  testing).

> **There is no `latest` tag for the console image.** It is published by version
> only (`v0.9.8`, `v0.9`, `v0`), on purpose: the installer pins the exact digest
> of the release it ships with, and a floating tag would quietly undo that.
> `podman pull …-tui:latest` answers `manifest unknown` — that is the design,
> not a broken publish.

**Platforms.** The published image is `linux/amd64`, and the installer is POSIX
`sh`. Linux is the tested path. On **Windows, install inside WSL2** and treat it
as a Linux machine — there is no native Windows installer, and we are not going
to pretend otherwise. macOS and `arm64` are not published yet.

## 1. Install

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.9.8/scripts/install.sh | sh
```

### Inspect it before you run it

This is a wallet — reading the script first is a reasonable thing to want. Fetch
it to a file, read that file, then run **that same file**: what you read is
exactly what runs.

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.9.8/scripts/install.sh -o install.sh
less install.sh      # ~321 lines of POSIX sh
sh install.sh
```

> **What the tag in that URL is and is not.** It pins a *version* — it is not a
> cryptographic identity. A git tag can in principle be repointed at a different
> commit, so treat the tag as "which release", not as proof of content. The
> identities that are bound to exact bytes are the ones **inside** the script:
> the image `@sha256:` digest it pulls and the `sha256` of the shim it installs.
> For the script itself, the published `sha256` is the check.
>
> This is why reading the script and running *that same file* matters. The shim
> is fetched later than the script was, and the hash the script carries is what
> makes the bytes you get then match the release you read now — even if the tag
> moved in between.

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
3. Fetches the `rustok` shim over `--proto '=https' --tlsv1.2`, **verifies its
   `sha256` against the pin inside this script**, and only then makes it
   executable and installs it to `~/.local/bin`. A mismatch aborts and says so:
   the bytes at that URL changed since the script was published. If no hashing
   tool is available at all (`sha256sum`, `shasum`, `openssl`), the installer
   refuses rather than installing something it cannot check.
4. Adds `~/.local/bin` to your `PATH` in one marked block of your shell profile.
   Set `RUSTOK_NO_MODIFY_PATH=1` to skip that and get the line to add yourself.

It **never touches a secret, a keystore volume or your wallet.** Creating the
wallet — the part that prints your recovery phrase — is a separate step *you*
run in your own terminal. A recovery phrase must never travel through a pipe.

If `rustok` is not found afterwards, open a new shell (or `. ~/.bashrc`), then
run `rustok doctor`.

## 2. Create your wallet — `rustok init`

Run this in a **terminal the agent cannot see**. You choose one thing, and it
prints one thing exactly once:

- you **choose a 6-digit approval PIN** (typed twice) — the one code you will
  ever enter: it opens the console session and confirms payments;
- it **prints the 12-word recovery phrase** — your one backup.

```bash
rustok init
```

There is no password to remember. The keyring password that encrypts the keystore
is generated by `rustok init` itself (32 random bytes) and stored where the engine
keeps secrets — podman's secret store, or a `0600` file in your config dir
(`~/.config/rustok` by default) on docker. It never reaches your shell history,
`inspect`, any agent config file, or your eyes.

The PIN goes to the wallet over a pipe, never as a command-line argument or an
environment variable. A PIN the wallet finds too predictable (`000000`, `123456`,
`121212` and the like) is refused with a message — just run `rustok init` again
with a different one; nothing was created. Pick something that is not a date
either: a birthday is the one PIN the person next to you already knows, and the
console allows three tries before it locks for five minutes.

`rustok init` **refuses to run without a real terminal of your own**: through a
pipe or an agent shell it stops with a named error rather than printing a
recovery phrase into somewhere it should never appear.

Back up the **12 words** offline, then fund the printed address. The PIN is yours
to remember; if you forget it, `rustok set-pin` lets you choose another (see
[TROUBLESHOOTING](TROUBLESHOOTING.md#forgot-the-approval-pin)).

`init` creates **new** wallets and never touches an existing keystore: if the
wallet is already there it refuses and points you at `rustok restore`. `--force`
only replaces a keyring secret whose wallet volume is gone; over a live volume it
refuses too — a regenerated password could not open the keystore that is there.

### Where things live, and what each protects

| What | Where | Protected by |
|---|---|---|
| Your keys (`keystore.json`) | the wallet **volume** | AES-256-GCM under a 32-byte random password (Argon2id, 64 MiB × 3), file mode `0600` |
| That password | podman **secret store** / `0600` file in `~/.config/rustok` (docker) | your user account on this machine |
| Your approval PIN | only its Argon2id **hash**, in the volume | three tries, then a five-minute lockout — while the wallet runs |
| The 12 words | **nowhere** — the wallet does not store them | you: write them down offline |

**A copy of the volume alone is not a backup.** The password that opens it lives
outside the volume and is not something you know, so a volume restored on another
machine will not unlock. Your backup is the 12 words: `rustok restore` brings the
same address and the same funds back on a fresh volume (with a new PIN); what it
does not bring back is the payment journal and any settings.

## 3. Connect your agent — `rustok connect`

```bash
rustok connect claude     # writes ~/.claude.json
rustok connect cursor     # writes ~/.cursor/mcp.json
rustok connect hermes     # writes ~/.hermes/config.yaml
rustok connect openclaw   # writes ~/.openclaw/openclaw.json (via `openclaw mcp set`)
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
rustok              # open the approval console (starts the wallet if none is up)
rustok status       # which wallets are running, under which image
rustok doctor       # engine, PATH, jq/PyYAML, running wallets, leftovers
rustok start        # start this agent's wallet in the background
rustok stop         # stop it
```

**Closing the console puts away what it took out.** If `rustok` started the
wallet for you, quitting the console (`q`) stops it again and says so. If it
attached to a wallet that was already running — an agent's, or one you started
with `rustok start` — it leaves that one alone: stopping it would kill the
process an agent is talking to, and an approval waiting there lives in that
process's memory.

Closing the terminal window abruptly is not the same as quitting: the shim is
killed before it can tidy up, and a wallet it started keeps running. `rustok
stop` is the way back from that.

`rustok doctor` is the first thing to run when something looks wrong — it checks
the engine is actually responding, that `~/.local/bin` is on your `PATH`, and
that the optional tools `connect` needs are present.

## Updating

```bash
rustok update
```

Pulls the current wallet image and re-registers every rustok MCP entry it finds
across claude / cursor / hermes / openclaw, each keeping its own wallet. A failed pull stops
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

Your keys, address and PIN hash live in the **volume**, not in the image, so they
survive every update (the keyring password lives beside it, in the secret store —
also untouched by an update). Anything waiting for approval does not: the pending queue
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
rustok init --agent hermes        # its own keystore volume, secret and PIN
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

**Podman (recommended)** — store the password once in podman's secret store and
mount it as a *file*: it never touches shell history, `podman inspect` or the MCP
config, it is in no process's environment, and quotes in the password are safe
(they are read as-is, not parsed). `mode`/`uid`/`gid` narrow the mount from
podman's world-readable default to owner-only for the image's user:

```bash
read -r -s -p "Keyring password: " pw &&
  printf '%s' "$pw" | podman secret create rustok-keyring-claude -
unset pw

podman run -it --rm \
  -v rustok-wallet-tui:/data \
  --secret rustok-keyring-claude,type=mount,mode=0400,uid=1000,gid=1000 \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/rustok-keyring-claude \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8 create-wallet
```

**Docker** (no secret store without swarm) — keep the password in a `0600` file
and hand the wallet its *path* via `RUSTOK_KEYRING_PASSWORD_FILE` (a trailing
newline in the file is stripped). The path below is yours to choose; the shim
keeps its own at `~/.config/rustok/keyring-pass-<agent>`:

```bash
umask 077
read -r -s -p "Keyring password: " pw &&
  printf '%s' "$pw" > ~/.rustok-keyring-pass
unset pw

docker run -it --rm \
  -v rustok-wallet-tui:/data \
  -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8 create-wallet
```

#### What the file delivery does and does not protect

> Every boundary this wallet has is collected in one place: **[CAVEATS](CAVEATS.md)**.
> The list below is the part of it that concerns the password.

Worth reading once, because the difference decides which of the two commands
above you should use.

- **What it closes.** The password is in no process's `/proc/<pid>/environ`, so
  it cannot be harvested from a running wallet the cheapest way there is; it is
  not inherited by anything the agent spawns; and `podman inspect` holds a path,
  not the value.
- **The `-e` path is still accepted, and still leaks into the container config.**
  The entrypoint stages such a password in a `0600` file, drops the variable and
  deletes the file once the core has unlocked — but the copy the *runtime* keeps
  in the container config is outside the image's reach, and `--init` would add
  another holder for the container's life. That is why the commands above pass a
  file and no `--init`.
- **Same-user code is not in scope.** Anything already running as your user can
  read the mounted secret, the staged file during its short life, the core's
  memory and the data volume. This protects a secret from casual harvesting, not
  a machine from its own compromise.
- **Measured on podman 5.8.4.** Docker was not installed on the machine these
  runs were made on: the mechanism is engine-independent (a mounted file plus an
  environment variable naming its path), but docker's behaviour here is
  **expected, not verified**.

Either way, `create-wallet` run by hand like this — with nothing on its stdin —
prints the **12-word recovery phrase** and a **generated 6-digit approval PIN**
exactly once. (Through the shim you choose the PIN instead and only the phrase is
printed; that path is `rustok init`, above.) Back both up offline before going
further, then fund the printed address — nothing later in this appendix will
show them again.

### Register it with an agent

The MCP client launches the image over stdio — **the password never goes into
this config file**. With podman the secret above does the delivery:

```json
{
  "mcpServers": {
    "rustok": {
      "command": "podman",
      "args": ["run", "-i", "--rm",
               "--label", "rustok=wallet", "--label", "rustok.agent=claude",
               "-v", "rustok-wallet-tui:/data",
               "--secret", "rustok-keyring-claude,type=mount,mode=0400,uid=1000,gid=1000",
               "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/rustok-keyring-claude",
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
               "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
               "ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8"]
    }
  }
}
```

With **docker**, swap the `--secret` argument pair for the `0600`-file mount:

```jsonc
"command": "docker",
"args": ["run", "-i", "--rm",
         "--label", "rustok=wallet", "--label", "rustok.agent=claude",
         "-v", "rustok-wallet-tui:/data",
         "-v", "/home/you/.rustok-keyring-pass:/run/keyring-pass:ro",
         "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
         "-e", "RUSTOK_ALLOWED_CHAINS=1,8453",
         "-e", "RUSTOK_RPC_URLS_1=https://ethereum-rpc.publicnode.com",
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8"]
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

(To choose a new PIN, `rustok set-pin` — or by hand, `docker exec -i <id>
core-server set-pin` with the new PIN on its stdin; with nothing on stdin it
generates one and prints it once. Either way the wallet proves it holds the
keyring password before it changes anything.)

### A second agent, by hand

Give it a distinct volume and sub-label, and its own secret:

```jsonc
"args": ["run", "-i", "--rm",
         "--label", "rustok=wallet", "--label", "rustok.agent=hermes",
         "-v", "rustok-hermes:/data",                // its own wallet volume
         "--secret", "rustok-keyring-hermes,type=mount,mode=0400,uid=1000,gid=1000",
         "-e", "RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/rustok-keyring-hermes", …,
         "ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8"]
```

`create-wallet` that volume once (as above, with `-v rustok-hermes:/data` and its
own secret), and open its console with `--filter label=rustok.agent=hermes`.

### Upgrading by hand

Pull the new tag, restart the agent, keep the volume:

```bash
docker pull ghcr.io/rustok-org/rustok-wallet-tui:v0.9.8
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
