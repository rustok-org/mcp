# Troubleshooting

## "no wallet keystore … create one first"

The wallet hasn't been created in this volume yet. Run onboarding once (podman shown;
the docker `_FILE` variant is in [INSTALL](INSTALL.md#2-create-your-wallet-one-time)):

```bash
read -r -s -p "Keyring password: " pw && printf '%s' "$pw" | podman secret create rustok-keyring-claude - && unset pw

podman run -it --rm -v rustok-wallet-tui:/data \
  --secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1 create-wallet
```

Back up the printed 12 words and approval PIN, then start the agent again.

## "backend not ready" / the agent can't reach the wallet

- Confirm the engine is running and the image is pulled.
- Confirm the password actually reaches the container — podman
  `--secret …,type=env,target=RUSTOK_KEYRING_PASSWORD`, docker
  `RUSTOK_KEYRING_PASSWORD_FILE` + file mount — and that it matches the one used at
  `create-wallet` (a wrong password fails the unlock).
- Confirm the same `-v rustok-wallet-tui:/data` volume is mounted as at onboarding.

## "RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file" / "… is empty"

The named errors of the `_FILE` delivery — the container refuses to start instead of
hanging on a missing password:

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

The PIN is printed only during `create-wallet`. If you lost it, run:

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" core-server set-pin
```

This requires the keyring password and an interactive TTY.

## "container name already in use" / cannot create container

You launched the wallet with a fixed `--name`. The agent-launched container must
**not** use `--name` — a fixed name collides the moment a health probe or a second
`mcp list` starts another instance. Use `--label rustok=wallet --label
rustok.agent=<agent>` instead (as in [INSTALL](INSTALL.md#3-connect-an-agent-stdio));
the container then runs under an auto-generated name and stays discoverable by label.
A leftover named container from an older setup: `docker rm -f rustok-wallet-tui`.

## The console command prints "'docker exec' requires at least 2 arguments"

The label-discovery one-liner substituted an **empty** container id, so `docker
exec -it "" …` has nothing to run in. Two causes:

- **The wallet isn't running.** The agent-launched container only exists while the
  agent session is live. Start (or restart) the agent session, then open the
  console. Check with `docker ps --filter label=rustok=wallet` — an empty list
  means no wallet is up.
- **Two containers share the same `rustok.agent` label** (a duplicate launch). The
  same `docker ps --filter label=rustok=wallet` shows both; stop the extra one, or
  give each agent a distinct `rustok.agent=<name>` (see
  [Running a second agent](INSTALL.md#running-a-second-agent)).

## After an upgrade the wallet looks empty / the agent still runs the old version

The wallet lives in the volume, not in the image: start the new image with the **same**
`-v rustok-wallet-tui:/data` and your address, keys and PIN come back. A different
volume name is a different (empty) wallet. If the agent still behaves like the old
build, the image tag in its MCP config is stale — the agent spawns the container itself.
See [Upgrading the wallet image](INSTALL.md#upgrading-the-wallet-image).

A transaction the agent parked but nobody approved does **not** survive a restart (the
pending queue is in the container's memory). Nothing was signed or sent — ask the agent
to propose it again.

## Empty balances / positions for a chain

That chain has no RPC configured. Set `RUSTOK_RPC_URLS_<chain>` (or
`RUSTOK_ALCHEMY_API_KEY`) and include the chain in `RUSTOK_ALLOWED_CHAINS`.
Example: `-e RUSTOK_ALLOWED_CHAINS=1 -e RUSTOK_RPC_URLS_1=https://…`.

## Tools not appearing (Claude Desktop / Cursor)

1. Fully restart the client (quit, not just close the window).
2. Check the MCP config path:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
3. Validate the JSON, and confirm `docker` is on PATH for the client.
4. The client must grant `read_wallet` / `preview_tx` / `execute_tx` for the
   corresponding tools to be listed/callable.

## "permission denied" on the volume

The container runs as uid/gid 1000. A **named** volume (`rustok-wallet-tui`) is
created with the right ownership automatically; prefer it over a host-path mount.

## Getting help

- [GitHub Issues](https://github.com/rustok-org/mcp/issues)
- [Security](../SECURITY.md)
