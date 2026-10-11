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

## Signature verification refuses installation/update

Trusted **cosign 3+** is mandatory. Install it independently through a trusted system package channel; see [Sigstore installation](https://docs.sigstore.dev/cosign/system_config/installation/). A missing/non-executable/broken verifier, cosign 2.x, a wrong identity/issuer/signature, or unavailable verification network stops installation before persistent installation writes or client changes. Repair the verifier/network and retry the same signed release; removing the verifier does not bypass the check.

`verify-blob` authenticates the release manifest under release-shelf's fixed tag identity. `verify` authenticates the OCI image under wallet-publish on main. These are separate checks. Never execute a freshly downloaded installer before its hash and manifest signature have passed the published skill bootstrap.

A missing/corrupt local manifest stops normal launches; reinstall from the [published release skill](https://github.com/rustok-org/mcp/releases/download/wallet-tui-v0.12.0/SKILL.md). An installation lock may indicate another installer or an interrupted commit. Inspect it before removing a stale lock; do not delete wallet volumes/passwords to fix installation state.

## `neither podman nor docker found`

Install one — podman is recommended (rootless, and it ships the secret store the
wallet uses for the keyring password):
<https://podman.io/getting-started/installation>.

## "no wallet keystore … create one first"

The wallet has not been created for this agent yet:

```bash
rustok init                  # or: rustok init --agent hermes
```

You choose a 6-digit approval PIN and it prints the 12-word recovery phrase
exactly once — run it in your own terminal, never through an agent. Back the
words up, then start the agent again.

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

## `connect needs jq` / `connect hermes needs python3 with PyYAML` / `openclaw CLI not found`

`rustok connect` edits your agent's config file and refuses to do that with
string surgery. Install what it names (`dnf install jq` / `apt install jq`;
Hermes itself ships python3 + PyYAML). `connect openclaw` needs jq **and** the
`openclaw` CLI itself: the registration is written through `openclaw mcp set`,
never by editing that config behind its back. No other rustok command needs any
of them — `rustok doctor` reports all three as informational.

## `openclaw mcp unset rustok` fails with `Config write rejected … size-drop`

That is OpenClaw's own guard against a config write **made through its CLI**
when the file shrinks too far. Removing a large entry can trip it, and
`openclaw config unset mcp.servers.rustok` hits the same guard (measured:
`1069->492` and `1069->526`, both refused).

What works, measured end to end:

```bash
openclaw doctor --fix          # writes the defaults back: 1069 -> 2868 bytes,
                               # the rustok entry is still there
openclaw mcp unset rustok      # now succeeds: 2868 -> 2291, entry gone
```

`doctor --fix` helps by raising the size the guard compares against, not by
restoring a backup. `rustok uninstall` relays OpenClaw's own message and this
order when it hits the refusal, instead of repeating the command that failed.

Editing the config file directly — outside OpenClaw — is **not** gated by that
guard: the change sticks, and `openclaw doctor` without `--fix` does not undo it
(measured). OpenClaw notices the external edit and prints one line about it,
`Config observe anomaly … size-drop-vs-last-good` — a different guard on a
different path, which is why that token never appears in the write refusal
above.

## On docker: the wallet never unlocks, as if no password reached it

The `_FILE` password delivery needs a wallet image that understands it —
**0.8.0 or newer**. The image published as `v0.7.1` was built a day before that
support landed, so it starts without a password and never unlocks. This used to
be a docker-only trap, because podman's secret arrived as a plain environment
variable; since **0.8.3** both engines deliver a file, so an image older than
0.8.0 fails the same way on either.

Check which image is actually running:

```bash
rustok status      # the IMAGE column shows the tag in use
```

If it is older than `v0.8.0`, **re-run the installer** — do not stop at
`rustok update`:

Use the [published release bootstrap](https://github.com/rustok-org/mcp/releases/download/wallet-tui-v0.12.0/SKILL.md) to migrate an old unsigned installer. The current `rustok update` verifies a signed release; use `--release 0.12.0` to choose it explicitly, or omit the flag to refresh the installed release. It preserves explicit subsets, narrows implicit grants and leaves live sessions running until a human restart.

## "backend not ready" / the agent can't reach the wallet

- `rustok status` — is a wallet actually running? The MCP client starts it when
  the agent session starts.
- `rustok doctor` — is the engine responding at all?
- Was the password stored with a **different** wallet than the one mounted? A
  wrong password fails the unlock. Re-store it with `rustok init --force`
  (keys untouched).
- Hand-rolled setup: confirm the same `-v rustok-wallet-tui:/data` volume is
  mounted as at onboarding, and that the password reaches the container
  (podman `--secret <name>,type=mount,mode=0400,uid=1000,gid=1000` plus
  `-e RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/<name>`; docker
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

Unlock fails with a wrong keyring password. Through the shim this cannot happen
by typing — `rustok init` generates and stores that password itself and you never
enter it. If you see it anyway, the stored secret and the keystore volume have
been separated: the volume was copied to another machine without its secret, or
the secret was removed and re-created. There is no reset for the password — the
way back is the 12 words: `rustok restore` onto a fresh volume.

If you run the container by hand (no shim) and typed the password yourself, use
the one you typed at `create-wallet`.

## Forgot the approval PIN

Choose a new one — the old PIN is not needed, the wallet checks its own keyring
password instead:

```bash
rustok set-pin                  # or: rustok set-pin --agent hermes
```

Run it in your own terminal, **with the wallet running**. Note that `rustok console`
starts the wallet but also stops it again when you leave — so either run
`rustok start --agent <name>` first and then `set-pin`, or run `set-pin` from a
second terminal while the console is open. By hand, without the shim: `docker exec -i <id> core-server set-pin` with
the new PIN on its stdin; with nothing on stdin it generates one and prints it
once. Either way the wallet proves it holds the keyring password before it
changes anything, so a copy of the volume without the secret cannot rotate the PIN.

## Lost the machine, or the volume — bringing a wallet back

Your backup is the 12 words. On the new machine, after installing:

```bash
rustok restore                  # or: rustok restore --agent hermes
```

It asks for the phrase on one line, then for a new PIN, and prints the address
it restored — check it against the one you expect. Same address, same funds; the
payment journal and settings do not travel with the words. A copy of the wallet
volume by itself is **not** a backup: the password that opens it lives outside
the volume and is not something you know.

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

The wallet lives in the volume, not in the image: the same volume (with its
secret still in the store) brings your address, keys and PIN back. A different
volume name is a different (empty) wallet.

- A wallet that was **running** during `rustok update` keeps the previous image
  until its agent's next session (or until `rustok stop`) — restart the agent.
- Hand-rolled setup: the image tag in the agent's MCP config is stale — the agent
  spawns the container itself. `rustok connect <client> --force` rewrites it.
- A transaction the agent parked but nobody approved does **not** survive a
  restart. Pending and active executions may be indistinguishable; an unknown
  outcome requires audit/hash/network investigation, never automatic replay.

`rustok update` verifies a signed release, including the installer and immutable image, before registering clients. Live sessions retain their previous image/grants until a human restart. Stop new requests in all sessions, resolve pending approvals, wait for active execution terminal results, then confirm `rustok stop`. This is human coordination, not a software drain guarantee.

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
