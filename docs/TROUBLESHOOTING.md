# Troubleshooting

**Start here:** `rustok doctor`. It checks the container engine is installed *and
responding*, that `~/.local/bin` is on your `PATH`, whether the optional tools
`rustok connect` needs are present, which wallets are running, and whether an old
fixed-name container is still lying around.

## `rustok: command not found`

The shim is installed to `~/.local/bin`, which your current shell may not have on
`PATH` yet.

- Open a new shell, or `. ~/.bashrc` (`~/.zshrc`, `~/.profile`).
- Installed with `RUSTOK_NO_MODIFY_PATH` set? Then nothing was added on purpose —
  add `export PATH="$HOME/.local/bin:$PATH"` yourself.
- Otherwise run `~/.local/bin/rustok doctor` directly; it will tell you the same.

## The installer says cosign is required

```
cosign is required to verify the wallet image signature — install it: …
```

The installer verifies the image's signature *before* writing anything to disk,
so [cosign](https://docs.sigstore.dev/cosign/installation) is a hard requirement
rather than an optional extra. No other rustok command uses it.

## `cosign could NOT verify …` — the installer refuses to install

Working as intended: the image did not verify against this repository's
publishing workflow, and nothing was written to disk. Causes, in order of
likelihood:

- **the release has not published its signed image yet** — check the release
  notes for the tag you are installing from;
- you edited the pinned digest or identity in a local copy of `install.sh`;
- something is actually wrong with the image. Do not work around it by skipping
  verification — that is the one guarantee the pipe-to-shell install rests on.

## `neither podman nor docker found`

Install one — podman is recommended (rootless, and it ships the secret store the
wallet uses for the keyring password):
<https://podman.io/getting-started/installation>.

## "no wallet keystore … create one first"

The wallet has not been created for this agent yet:

```bash
rustok init                  # or: rustok init --agent hermes
```

It prints the 12-word recovery phrase and the approval PIN exactly once — run it
in your own terminal, never through an agent. Back both up, then start the agent
again.

## `multiple wallets running: claude, hermes — use --agent <name>`

More than one wallet is up, so a bare command would have to guess which one you
mean — it refuses instead. Name it:

```bash
rustok console --agent claude
rustok stop --agent hermes
```

If the list contains `(unlabeled)`, that wallet predates the label model: add
`--label rustok.agent=<name>` to its launch config (see
[INSTALL](INSTALL.md#running-a-second-agent)), or re-register it with
`rustok connect <client> --force`.

## `connect needs jq` / `connect hermes needs python3 with PyYAML`

`rustok connect` edits your agent's config file and refuses to do that with
string surgery. Install what it names (`dnf install jq` / `apt install jq`;
Hermes itself ships python3 + PyYAML). No other rustok command needs them —
`rustok doctor` reports both as informational.

## On docker: the wallet never unlocks, as if no password reached it

The `_FILE` password delivery docker uses needs a wallet image that understands
it — **0.8.0 or newer**. The image published as `v0.7.1` was built a day before
that support landed, so on docker it starts without a password and never unlocks.
Podman is unaffected (its secret arrives as a plain environment variable).

Check which image is actually running:

```bash
rustok status      # the IMAGE column shows the tag in use
```

If it is older than `v0.8.0`, **re-run the installer** — do not stop at
`rustok update`:

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.8.0/scripts/install.sh | sh
```

The image version is chosen by the **shim**, and the shim does not update itself.
An old shim keeps pulling its own old tag *and* re-stamps that tag into your
agent's config on every `rustok update` — so editing the config by hand does not
survive either. Reinstalling is the only path that moves you forward, and it is
the one that verifies the signature.

## "backend not ready" / the agent can't reach the wallet

- `rustok status` — is a wallet actually running? The MCP client starts it when
  the agent session starts.
- `rustok doctor` — is the engine responding at all?
- Was the password stored with a **different** wallet than the one mounted? A
  wrong password fails the unlock. Re-store it with `rustok init --force`
  (keys untouched).
- Hand-rolled setup: confirm the same `-v rustok-wallet-tui:/data` volume is
  mounted as at onboarding, and that the password reaches the container
  (podman `--secret …,type=env,target=RUSTOK_KEYRING_PASSWORD`, docker
  `RUSTOK_KEYRING_PASSWORD_FILE` + file mount).

## "RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file" / "… is empty"

The named errors of the `_FILE` delivery — the container refuses to start instead
of hanging on a missing password:

- **Wrong path**: the value of `RUSTOK_KEYRING_PASSWORD_FILE` must match the mount
  target (podman secret default: `/run/secrets/<secret-name>`).
- **Secret not created**: check `podman secret ls`.
- **SELinux host** (Fedora and friends): a bind-mounted file needs the `:z` mount
  option, or the container is denied the read.
- **Not a regular file**: a directory, FIFO or device at that path is refused.
- **"is empty"**: the file has no content — recreate it with `printf '%s' "$pw" > file`
  (an `echo`-made file with only a newline counts as empty after stripping).

## Wrong password

Unlock fails with a wrong password. There is no reset — use the correct password,
or recover from the 12-word phrase into a fresh wallet.

## Forgot the approval PIN

The PIN is printed only when the wallet is created. If you lost it, reset it in
the running wallet (this needs the keyring password and an interactive TTY):

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" core-server set-pin
```

## "container name already in use" / cannot create container

You launched the wallet with a fixed `--name`. The agent-launched container must
**not** use one — a fixed name collides the moment a health probe or a second
`mcp list` starts another instance. Use `--label rustok=wallet --label
rustok.agent=<agent>` instead (as in
[INSTALL](INSTALL.md#appendix-installing-without-the-shim)); the container then
runs under an auto-generated name and stays discoverable by label. A leftover
named container from an older setup: `docker rm -f rustok-wallet-tui`
(`rustok doctor` warns when it sees one).

## The console command prints "'docker exec' requires at least 2 arguments"

The by-hand label-discovery one-liner substituted an **empty** container id, so
`docker exec -it "" …` has nothing to run in. `rustok console` handles both
causes for you; by hand, they are:

- **The wallet isn't running.** The agent-launched container only exists while
  the agent session is live. Check with `rustok status` (or
  `docker ps --filter label=rustok=wallet`) — an empty list means no wallet is up.
- **Two containers share the same `rustok.agent` label** (a duplicate launch).
  Stop the extra one, or give each agent a distinct `rustok.agent=<name>` (see
  [Running a second agent](INSTALL.md#running-a-second-agent)).

## After an update the wallet looks empty / the agent still runs the old version

The wallet lives in the volume, not in the image: the same volume brings your
address, keys and PIN back. A different volume name is a different (empty)
wallet.

- A wallet that was **running** during `rustok update` keeps the previous image
  until its agent's next session (or until `rustok stop`) — restart the agent.
- Hand-rolled setup: the image tag in the agent's MCP config is stale — the agent
  spawns the container itself. `rustok connect <client> --force` rewrites it.
- A transaction the agent parked but nobody approved does **not** survive a
  restart (the pending queue is in the container's memory). Nothing was signed or
  sent — ask the agent to propose it again.

> Note on trust: `rustok update` **pulls by tag** and
> **does not re-run the cosign verification** — the signature check belongs to
> `install.sh`, so it covers installation, not the whole lifecycle. Re-running
> the installer for a new release gives you the verified path again.

## Empty balances / positions for a chain

That chain has no RPC configured. Set `RUSTOK_RPC_URLS_<chain>` (or
`RUSTOK_ALCHEMY_API_KEY`) and include the chain in `RUSTOK_ALLOWED_CHAINS`, then
re-run `rustok connect <client> --force` so the registration picks it up.

## Tools not appearing (Claude Desktop / Cursor)

1. Fully restart the client (quit, not just close the window).
2. Confirm the registration landed: `rustok status` after starting a session, and
   check the client's own MCP list.
3. Hand-written config? Validate the JSON, and confirm the engine binary is on
   `PATH` for the client.
4. The client must grant `read_wallet` / `preview_tx` / `execute_tx` for the
   corresponding tools to be listed/callable.

## "permission denied" on the volume

The container runs as uid/gid 1000. A **named** volume (`rustok-wallet-tui`) is
created with the right ownership automatically; prefer it over a host-path mount.

## Getting help

- [GitHub Issues](https://github.com/rustok-org/mcp/issues)
- [Security](../SECURITY.md)
