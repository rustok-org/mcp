---
name: rustok-wallet-tui
description: Self-custody Ethereum agent wallet. Installs with one command and runs entirely on your machine as a single container image (MCP over stdio); private keys never leave it. Read wallet context, balances and DeFi positions (Aave v3, ERC-4626); preview transactions. Sending funds on-chain is gated in a separate terminal console, never inside the agent chat: you approve each payment, or confirm autonomous mode once and the wallet sends on its own after that; message signing is refused outright, in every mode. You assume all risk for funds on the agent wallet — there are no hard-coded spending limits.
version: 0.11.0
metadata:
  openclaw:
    emoji: "🦀"
    homepage: https://github.com/rustok-org/mcp
---

# rustok-wallet-tui

> **License note:** this OpenClaw skill package (`skills/rustok-wallet-tui/`) is MIT-0
> per ClawHub requirements. The Rustok wallet core itself is proprietary; only the
> compiled binary image is distributed.

You are connected to a **self-custody** Ethereum agent wallet that runs entirely
on the user's machine as a single Docker image (`ghcr.io/rustok-org/rustok-wallet-tui`).
The container runs the wallet core + gateway and speaks MCP over **stdio**; the
private keys live only in the user's local Docker volume and never leave it.

> ⚠️ **Self-custody, real funds, your risk.** This wallet has **no hard-coded
> spending limits or budgets** — the user consciously accepts that funds sent to
> the agent wallet are at risk. txguard still flags risky transactions, but it
> does not block them. All supported chains the user enables are live (incl.
> Ethereum mainnet). Always preview before executing and show the user the details.

## What's protected — and what isn't (be honest with the user)

The wallet's guarantee is narrow and specific. State it plainly; do not oversell it.

The full list of boundaries — password delivery, updates, what we do not verify at
all — lives in [docs/CAVEATS.md](https://github.com/rustok-org/mcp/blob/main/docs/CAVEATS.md).

| | |
|---|---|
| **Protected** | Private keys stay in the user's **local Docker volume** and never leave the machine. **Sending funds on-chain** (`execute_transaction`) is gated in a **separate console window** (`rustok console`, opened by the user — see below): parked for the user's approval, with a PIN for high-risk items — unless the user has confirmed **autonomous mode** there, a confirmation only they can give, once per wallet. |
| **Refused, not gated** | `sign_message` (EIP-191) is **refused outright** — in every mode, autonomous included. The console never sees a signature request, because signing does not happen at all: parking a signature for approval (`kind:sign`) is planned and not built. A tool that is listed and always refuses is neither a capability to rely on nor a hole to fear. Tell the user that rather than letting them plan around a signature. |
| **Outside the model** | An agent with **shell / `docker exec` access to the container** can read the gateway key and reach the full signing surface (including EIP-712 permits — a classic drain). That is why the console is a **separate window, not an agent command**. Trusting your own agent is the user's call, the same as never pasting a seed phrase into an untrusted tool. |

**Never claim** the agent (or a prompt-injected agent) "cannot move funds." What is
true: keys stay local, and **on-chain sends** are human-gated in the console.

### The mode switch, and why a send may still park

The user switches the wallet's mode **in the console**: press **`c`** on the
Dashboard, pick `read_only` / `supervised` / `autonomous`, enter the PIN. That
is how autonomy is turned ON — and OFF: switching back to `supervised` parks
every future send again, and `read_only` refuses every write outright. The
agent cannot flip that switch, and neither can an environment variable or a
launch flag. Until a human has confirmed autonomy there, an autonomous-looking
wallet **parks every send** exactly like a supervised one.

**Turning autonomy on does not release what already waits.** A payment parked
before the switch stays parked — it goes out when the user releases it in the
console, or expires. Do not retry it: a retry adds a second parked copy that
will be paid separately if released, and switching the mode releases neither
of them.

**Your session reads the wallet's mode once, when it connects.** If the user
switches the mode mid-session, your tool list does not change until the next
connect — a tool you still see may now be refused by the core. The refusal is
the wallet enforcing the new mode; tell the user what it said, do not retry
around it.

Confirmation from a messenger does not exist yet — the console is the only
place the switch can be thrown.

## What changed in 0.9.8

- **`sign_message` is refused outright, and these texts finally say so.** Every
  earlier release described it as an ungated hole you had to guard against. It is
  not a hole and not a protection: signing is an unfinished capability, and
  parking a signature for approval is planned and not built. Live acceptance of
  0.9.7 asked the wallet and got a refusal; nine texts had said otherwise.

## What changed in 0.9.7

- **The wallet states what it does not promise.** A `## Legal` section below, and
  a full [DISCLAIMER](https://github.com/rustok-org/mcp/blob/main/DISCLAIMER.md)
  that names the limit of every safeguard — starting with the one easiest to read
  as absolute: autonomous mode sends without asking once confirmed.

## What changed in 0.9.5

- **Gas limits now carry headroom.** A limit set to exactly the estimate turned
  any drift between estimating and executing into a burnt fee — a contract call
  could pay its gas and do nothing. Plain transfers were never affected.
- **ERC-20 tokens are documented at last** (see below). The wallet has been able
  to report registered tokens since 0.9.4, but nothing here said so, and an
  unregistered token reads exactly like an absent one.
- **`rustok connect --force` names what it is about to drop** instead of quietly
  rebuilding the registration from the current shell.

## Prerequisites

- **Podman** (recommended) or **Docker**. **cosign is optional** — the installer
  pulls the image **by digest** (you get exactly those bytes or nothing), and
  uses cosign, when it is present and runnable, to verify *who built* it
  (provenance). A missing or broken cosign is reported and skipped, not treated
  as a failure; a working cosign that disagrees still stops the install. Use
  cosign 3+ if you install it — 2.x cannot read our signatures.
- An Ethereum RPC URL (an Alchemy key URL is best; a public RPC works for testing).

## One-time onboarding (the user does this in their own terminal, once)

Three commands, in a **terminal the agent cannot see** — the full guide is
[docs/INSTALL.md](https://github.com/rustok-org/mcp/blob/main/docs/INSTALL.md).

**1. Install the `rustok` command.** Fetch the installer to a file, read that
file, then run **that same file** — what you read is exactly what runs. This is a
wallet: fetching a script straight into a shell means running code you never saw,
and one look costs less than that trade.

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.11.0/scripts/install.sh -o install.sh
less install.sh      # ~321 lines of POSIX sh
sh install.sh
```

It pulls the wallet image **by digest** (those bytes or nothing) and verifies who
built it with cosign when cosign is available.

<details>
<summary>The one-liner, if you have already read the script</summary>

```bash
curl --proto '=https' --tlsv1.2 -fsSL \
  https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-v0.11.0/scripts/install.sh | sh
```

Piping to a shell runs whatever the URL serves at that moment, unreviewed. The
tag pins a *version*, not the bytes — the identities bound to exact bytes live
**inside** the script (the image digest and the shim's commit SHA). Fine once you
have read it; not the way to meet it.
</details>

**2. Create the wallet** — the user chooses a 6-digit approval PIN; it prints the
12-word phrase ONCE:

```bash
rustok init
```

**3. Register this wallet with the agent client:**

```bash
rustok connect claude
```

`rustok init` asks the user to choose a **6-digit approval PIN** (typed twice) —
the one code they will ever enter: it unlocks the console session and confirms
payments. The keyring password that encrypts the keystore is generated by `init`
itself and kept in the engine's secret store; the user never sees or types it,
and it never reaches shell history, `inspect` or any config file. `init` prints
exactly one thing, once: the **12-word recovery phrase**.

The 12 words are the only backup — write them down offline; the wallet does not
store them. Recovery is `rustok restore` (or importing the words into any standard
BIP-39 wallet — same address). A copy of the wallet volume by itself is **not** a
backup: the password that opens it lives outside the volume and is not something
the user knows. If the PIN is forgotten, `rustok set-pin` lets them choose a new
one — the old PIN is not needed.

> **Rule of two windows:** never run `rustok init`, `rustok restore`,
> `rustok set-pin` or the approval console through an agent shell/command — the
> seed and PIN would leak into the agent's context. These belong only in the
> user's own terminal (window 2). Do not ask the user for their PIN or their
> phrase in this chat, ever.

## Where the balance you show comes from

The wallet reads chains through an RPC node. Since 0.11.0 it carries two public
endpoints for each chain it shows (Ethereum, Base, Arbitrum by default), so a
fresh install reports balances without the user configuring anything, and USDC
appears beside the native coin without being registered.

**Tell the user this when it matters, and never as a footnote to a payment:** any
node that reads a balance learns the address and the IP that asked — the
carried ones, one they name themselves, and their own provider's alike. They
replace the carried list with `RUSTOK_RPC_URLS_<chain>`; naming one replaces the
list rather than adding to it.

On Arbitrum two USDC rows are normal: the native token and the bridged one, which
the wallet labels `USDC.e`. On chain both call themselves `USDC` — only the
contract address separates them, which is why balance rows carry it. Never treat
them as one balance, and never sum them without saying you did.

## How the agent runs the wallet

`rustok connect claude` writes this registration for the user, so normally none of
it is typed by hand. It is reproduced here as the reference for what a correct
setup looks like — and for setups built without the shim.

The MCP client launches the image over stdio (keys stay local). **Never put the
keyring password in the MCP config or shell history.** On podman, store it once in
the secret store; on docker, keep it in a private `0600` file and pass its *path*:

```bash
# One-time (podman): the value never touches history, inspect or configs.
read -r -s -p "Keyring password: " pw &&
  printf '%s' "$pw" | podman secret create rustok-keyring-claude -
unset pw

podman run -i --rm \
  --label rustok=wallet --label rustok.agent=claude \
  -v rustok-wallet-tui:/data \
  --secret rustok-keyring-claude,type=mount,mode=0400,uid=1000,gid=1000 \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/rustok-keyring-claude \
  -e RUSTOK_ALLOWED_CHAINS="1,8453,42161" \
  -e RUSTOK_RPC_URLS_1="https://your-rpc" \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.11.0
```

```bash
# Docker variant: a 0600 file + RUSTOK_KEYRING_PASSWORD_FILE (path, not value).
umask 077
read -r -s -p "Keyring password: " pw &&
  printf '%s' "$pw" > ~/.rustok-keyring-pass
unset pw

docker run -i --rm \
  --label rustok=wallet --label rustok.agent=claude \
  -v rustok-wallet-tui:/data \
  -v ~/.rustok-keyring-pass:/run/keyring-pass:ro \
  -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass \
  -e RUSTOK_ALLOWED_CHAINS="1,8453,42161" \
  -e RUSTOK_RPC_URLS_1="https://your-rpc" \
  ghcr.io/rustok-org/rustok-wallet-tui:v0.11.0
```

> Legacy `--env-file` delivery still works but is deprecated: the value lands in
> `inspect`, and quotes inside an env-file become part of the password (a silent
> unlock failure). Migrate to the secret / `_FILE` delivery above.

> **Labels, not `--name`:** the agent launches this itself, and a fixed name
> collides with health probes / a second `mcp list`. The `rustok.agent` sub-label
> also lets a second agent run its **own** wallet (own volume) alongside.

> The container automatically mints an ephemeral `RUSTOK_MCP_API_KEY` for the
> loopback gateway↔mcp hop, so no API key configuration is needed for stdio use.
> Set `RUSTOK_MCP_API_KEY` yourself **only** when exposing the gateway over a
> network (not the default stdio setup).

When the agent asks the user to approve a transaction, the user opens the
console in a **second terminal** (window 2), never through the agent session:

```bash
rustok console
```

Without the shim, the container runs under an auto-generated name (labels, not
`--name`), so it is found by label:

```bash
docker exec -it "$(docker ps -q --filter label=rustok=wallet --filter label=rustok.agent=claude)" rustok-console
```

The console shows the decoded transaction from the wallet core and waits for
`y/N` (high-risk items also ask for the per-transaction PIN).

For **Claude Desktop / Cursor** (stdio MCP), this is the entry `rustok connect`
writes — or that the user adds by hand to the MCP config. The keyring
password is delivered by the podman secret (or the docker `_FILE` mount) above,
**never in this config file** — only the non-secret RPC URL lives here:

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
               "-e", "RUSTOK_ALLOWED_CHAINS=1,8453,42161",
               "-e", "RUSTOK_RPC_URLS_1",
               "ghcr.io/rustok-org/rustok-wallet-tui:v0.11.0"],
      "env": {
        "RUSTOK_RPC_URLS_1": "https://your-rpc"
      }
    }
  }
}
```

## Why Rustok exists

Rustok gives an AI agent a wallet of its own — self-custody, no middleman — so agents can begin
to take part in the economy directly: weighing what's worth paying for, covering the compute,
data, and tools they rely on, and in time commissioning and paying the people who help them.

## Tools

The stdio wallet image is process-trusted and exposes **all** tools by default.
To run a restricted agent, set `RUSTOK_MCP_CAPABILITIES` to a subset
(`read_wallet` / `preview_tx` / `execute_tx`) — e.g. `read_wallet` for read-only.
The ceiling is enforced by the gateway, on the path every request takes: it
covers the MCP tools below **and** the HTTP routes behind them, so a session
cannot reach past its capabilities by calling the gateway directly. In releases
before 0.9.0 the ceiling was checked in the MCP layer only, which left every
route reachable beside it: the core refused signing for its own unrelated
reasons, but a session narrowed away from `read_wallet` still read the wallet
address and every balance. A client may narrow its own session further in
`initialize`, and can never widen it.

| Tool | Capability | What it does |
|------|-----------|--------------|
| `get_wallet_context` | read_wallet | Active wallet address, the assets it holds (native coin + registered tokens), the assets it could not read, allowed chains |
| `get_balances` | read_wallet | Balances of the active wallet — one row per asset, with `balance_formatted` to show and `token_address` to tell two same-named tokens apart — or the native balance of `{address, chain_id}` |
| `get_positions` | read_wallet | DeFi positions — Aave v3 (collateral/debt/health factor/LTV) + ERC-4626 vaults; optional `{address}` |
| `preview_transaction` | preview_tx | Preview any transaction `{to, value, chain_id, data?}` → decoded call (who/what is authorized), pre-sign simulation (revert check), gas, risk level |
| `execute_transaction` | execute_tx | Submit a previewed transaction `{preview_id}` — parked for human approval on a supervised wallet, released by the core on one whose owner confirmed autonomous mode; a `pending` result carries `next_step` for the human |
| `get_execution_status` | execute_tx | Poll a parked execution `{preview_id}` → `pending` / `executed` (+`tx_hash`) / `denied` / `expired` / `failed` (+`error_reason`), with the `not_after_unix` deadline. **`executed` means broadcast, not on-chain success** — see below |

### ERC-20 tokens are opt-in — an empty list is not an empty wallet

The wallet reports the tokens the **user registered**, and never goes looking for
others. A wallet holding USDC shows no USDC until USDC is registered on that
chain:

```bash
-e RUSTOK_TOKENS_1="USDC:0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48:6"
-e RUSTOK_TOKENS_8453="USDC:0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913:6"
```

`SYMBOL:ADDRESS:DECIMALS`, comma-separated, one variable per chain, and the chain
must be listed in `RUSTOK_ALLOWED_CHAINS`. A malformed entry, a duplicate address
on one chain, or an unknown chain **fails startup** naming the chain — a
half-loaded registry is worse than none. Symbol and decimals are taken from the
user, not read from the contract: get the decimals wrong and the wallet will show
a wrong amount confidently.

**What this means for you, the agent:** before telling the user they hold none of
a token, say that it may simply not be registered. Reading an empty list as an
empty wallet is the likeliest way to be wrong here — and it has already happened.

## Behavioral guidelines

1. **Always `preview_transaction` first** and show its decoded call + simulation (revert check) + risk level so the user gives informed approval.
2. **The money path is preview → summary card → `execute_transaction` → human.**
   `execute_transaction` only parks the transaction (`state: "pending"`) — the user
   releases it in a separate terminal window by running `rustok console` (see
   the onboarding above). Never offer to run the console command yourself
   and never ask the user to paste the approval PIN into this chat.
3. **`executed` means the transaction was broadcast, not that it succeeded.**
   The wallet reports the hash the moment the network accepted the transaction
   for inclusion; a transaction that reverts on-chain still costs its gas and
   still reads as `executed` here. Verify the receipt independently before
   telling the user their swap or approval went through — an explorer, or
   `eth_getTransactionReceipt` where `status` must be `0x1`.
4. **Poll `get_execution_status` reasonably**: when the user asks, or every ~15–30
   seconds until the `not_after_unix` deadline (if it is `null` — only on request).
   Stop on any terminal state: `executed`, `denied`, `expired`, `failed`. A
   `denied` outcome is the human's answer — do not re-submit the same transaction;
   a not-found error means the id is no longer retained — stop polling.
5. **Surface what the preview decoded** (who/what is authorized, amount, revert check, estimated cost, risk level) before the user acts on it.
6. **Use `get_wallet_context` first** so you don't hallucinate balances or chains.
7. If a tool needs a capability the session lacks, it returns an authorization
   error — explain that to the user rather than retrying.
8. If the wallet is unreachable, tell the user the wallet container/onboarding may
   not be set up (see onboarding above).

## Legal

Provided **as is**, without warranty of any kind, under the MIT-0 license.
**What an agent does with this wallet is not an act of the authors:** the agent
driving it is third-party software whose output is unpredictable and may be
inaccurate, incorrect, or undesirable, and evaluating each proposed transaction
before approving it is the user's exclusive responsibility. Nothing this wallet
or the agent driving it produces is investment, accounting, legal, or tax advice.
Sending funds is gated at the console **unless autonomous mode was confirmed**;
**`sign_message` is refused outright** in every mode. The risk of loss is
substantial and the user assumes all of it.

Full terms, and every safeguard's limit named:
<https://github.com/rustok-org/mcp/blob/main/DISCLAIMER.md>
