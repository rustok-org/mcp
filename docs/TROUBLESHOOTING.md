# Troubleshooting

## "no wallet keystore … create one first"

The wallet hasn't been created in this volume yet. Run onboarding once:

```bash
docker run -it --rm --name rustok-wallet -v rustok-wallet:/data \
  -e RUSTOK_KEYRING_PASSWORD="your-password" \
  ghcr.io/rustok-org/rustok-wallet:v0.5.0 create-wallet
```

Back up the printed 12 words and approval PIN, then start the agent again.

## "backend not ready" / the agent can't reach the wallet

- Confirm Docker is running and the image is pulled.
- Confirm `RUSTOK_KEYRING_PASSWORD` is set and matches the password used at
  `create-wallet` (a wrong password fails the unlock).
- Confirm the same `-v rustok-wallet:/data` volume is mounted as at onboarding.

## Wrong password

Unlock fails with a wrong password. There is no reset — use the correct password,
or recover from the 12-word phrase into a fresh wallet.

## Forgot the approval PIN

The PIN is printed only during `create-wallet`. If you lost it, run:

```bash
docker exec -it rustok-wallet core-server set-pin
```

This requires the keyring password and an interactive TTY.

## "container name already in use" / cannot create container

The wallet runs as a singleton named `--name rustok-wallet`. Stop the old
container first (`docker rm -f rustok-wallet`) if a previous run is still alive.

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

The container runs as uid/gid 1000. A **named** volume (`rustok-wallet`) is
created with the right ownership automatically; prefer it over a host-path mount.

## Getting help

- [GitHub Issues](https://github.com/rustok-org/mcp/issues)
- [Security](../SECURITY.md)
