# Troubleshooting

## The MCP client times out connecting (30 s, silently)

You are on image **≤ 0.4.0**: its JSON-RPC responses were malformed
(`"error": null` next to `result`), which strict clients (Claude Code 2.1+)
reject without a word — the handshake dies as a silent 30 s timeout. Fixed in
**0.4.1**: pull `ghcr.io/rustok-org/rustok-wallet:latest` again and restart
the agent. No config changes needed.

## "no wallet keystore … create one first"

The wallet hasn't been created in this volume yet. Run onboarding once —
see [Installation](INSTALL.md) step 2 (secret / `_FILE` password delivery).
Back up the printed 24 words, then start the agent again.

## "RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file"

The `_FILE` path is wrong or the file is not a regular readable file:
- The path is **inside the container** — the file must be mounted there
  (`-v ~/.rustok-keyring-pass:/run/keyring-pass:ro` on docker; on podman prefer
  the `--secret …,type=env` delivery, no file at all).
- A directory, device or FIFO at that path is refused by design.
- Rootless **podman** hands a host `0600` bind-mount to the container
  root-owned — unreadable for the in-container user. Use the
  `--secret …,type=env,target=RUSTOK_KEYRING_PASSWORD` delivery instead.

## "RUSTOK_KEYRING_PASSWORD_FILE is empty"

The mounted password file has no content (or only a trailing newline, which is
stripped). Rewrite it: `umask 077 && printf '%s' "$pw" > ~/.rustok-keyring-pass`.

## "backend not ready" / the agent can't reach the wallet

- Confirm Docker/Podman is running and the image is pulled.
- Confirm the password arrives (secret or `_FILE`) and matches the password
  used at `create-wallet` (a wrong password fails the unlock).
- Confirm the same `-v rustok-wallet:/data` volume is mounted as at onboarding.

## Wrong password

Unlock fails with a wrong password. There is no reset — use the correct
password, or recover from the 24-word phrase into a fresh wallet.

If you wrote the password into a `_FILE` by hand (not via the `read -s` +
`printf '%s'` recipe in [Installation](INSTALL.md)) and it has quotes in it —
e.g. `echo "my'pass" > ~/.rustok-keyring-pass` — the quote characters become
**part of the password**, a silent mismatch. Rewrite the file with
`printf '%s' "$pw" > ~/.rustok-keyring-pass` (no quoting, no trailing newline).

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
3. Validate the JSON, and confirm `docker` (or `podman`) is on PATH for the client.
4. Over stdio the wallet exposes all tools by default; if you set
   `RUSTOK_MCP_CAPABILITIES` to a subset, the gated tools are hidden on purpose.

## "permission denied" on the volume

The container runs as uid/gid 1000. A **named** volume (`rustok-wallet`) is
created with the right ownership automatically; prefer it over a host-path mount.

## Getting help

- [GitHub Issues](https://github.com/rustok-org/mcp/issues)
- [Security](../SECURITY.md)
