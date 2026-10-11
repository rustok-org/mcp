# Caveats — what this wallet does not guarantee

Every security property has an edge. This file names ours, in one place, so the
answer does not have to be reassembled from a changelog entry, an install page
and a troubleshooting note — which is how it was answered three separate times
before this file existed.

Nothing here is a known bug. These are the boundaries of guarantees we *do*
make. A boundary you can see is worth more than one you have to discover.

The form is borrowed from [seL4's `CAVEATS.md`](https://github.com/seL4/seL4/blob/master/CAVEATS.md),
including the habit that produced it: their proof file for non-interference opens
by stating that the property in its own filename *"does not hold on the kernel and
is not proven"*. Naming the gap where it is easiest to stay quiet is the standard
worth copying.

---

## The keyring password

**What holds.** Delivered the documented way — a mounted file plus
`RUSTOK_KEYRING_PASSWORD_FILE` — the password is in no process's
`/proc/<pid>/environ` inside the container, and `podman inspect` carries the path
rather than the value. Delivered the compatibility way (`-e`), the entrypoint
stages it in a `0600` file, drops the variable, hands the core a path, and removes
the file once the keystore is unlocked; every exit path removes it, including the
failure timeouts.

**What does not hold.**

- With `-e` delivery the value still sits in the **container config** (`podman
  inspect`) and, under `--init`, in the **runtime's own PID 1**. Neither is
  reachable from inside the image. This is why the file delivery is the documented
  one and `--init` is absent from every command we publish.
- Nothing here defends against **code already running as your user**. It can read
  the mounted secret, the staged file during its short life, the core's memory,
  and the data volume.
- Measured on **podman 5.8.4**. Docker is not installed on the machine these runs
  were made on: the mechanism is engine-independent (a mounted file plus a variable
  naming its path), but docker's behaviour here is **expected, not verified**.

## Keys and the approval gate

**What holds.** Private keys stay in your local volume. On the console edition,
`execute_transaction` is parked and needs your approval in a **separate console
window**, with a PIN for high-risk items. `keystore.json` and `approval-pin.json`
are owner-only (`0600`), and installs that predate that are narrowed at startup.
The keyring password that encrypts the keystore is 32 random bytes the shim
generates — stronger than anything a person would type — and lives in the
engine's secret store, outside the volume.

**The PIN is yours to choose — and that is a trade.** It used to be minted at
random; now you choose the PIN at `rustok init`, so there is one code instead of two.
The cost is named here rather than hidden: a chosen 6-digit PIN is not uniformly
random. The wallet refuses the obvious ones (`000000`, `123456`, `121212`,
`123123` and their kind) but **does not refuse dates** — a birthday is the one
PIN the person next to you already knows, and the console grants three tries
before a five-minute lockout. Pick something that is not a date. The offline case
is unchanged: a copy of `approval-pin.json` can be brute-forced at leisure (it is
an Argon2id hash, 64 MiB × 3, but six digits are six digits) — and a guessed PIN
without the keystore's password opens nothing, which is why that password is now
random rather than yours.

**What does not hold.**

- **Switching the mode does not touch what already waits.** Turning autonomy on
  releases nothing: a payment parked before the switch stays parked until you
  release it in the console or it expires. And an agent session reads the
  wallet's mode once, at connect — switch the mode mid-session and the agent's
  tool list lags until its next connect, while the core already enforces the
  new mode on every call. The lag is cosmetic; the enforcement is not.
- **`sign_message` is refused outright**, in every mode, autonomous included. The console never
  sees a signature request, because signing does not happen at all yet: parking a
  signature for approval (`kind:sign`) is planned and not built. Do not plan around
  a signature this wallet can produce — it cannot.
- **A parked transaction lives exactly as long as the wallet session.** Close the
  agent session while something waits for your decision and the parked item is gone
  — it is not queued anywhere, and reopening the console will not find it. That is
  deliberate: a stale approval that outlives the conversation which proposed it is
  worse than one that expires. It means the practical rule is "keep the session open
  until you have decided", and that an agent asking you to approve something should
  wait for you rather than move on.
- **Shell access to the container defeats the gate.** Anything that can
  `docker exec` into it reads the gateway key — a `0600` file staged under `/run`
  — and reaches every route the configured `RUSTOK_MCP_CAPABILITIES` ceiling
  allows. Message and typed-data signing remain refused by the core in every mode; a compromised host can steal keys and bypass the client boundary. A narrower
  ceiling does now genuinely narrow this, because the gateway enforces it on the
  path; it does not make the caller harmless. That is why the console is a
  separate window and not an agent command.
- **`RUSTOK_MCP_CAPABILITIES` was decoration until 2026-08-04.** It was checked
  in the MCP layer only, and every tool's HTTP route sat beside that check rather
  than behind it. On the published agent image a session narrowed to
  `read_wallet` produced a real EIP-712 signature — measured, not reasoned about.
  It is enforced in the gateway now, on both editions. If you ran a narrowed
  session before this release, assume it had full access.
- **The agent edition (`rustok-wallet` 0.4.x) has no approval gate at all.** It
  executes autonomously by design — that is the difference between the editions,
  not an oversight.
- **There are no spending limits.** `txguard` flags risky transactions; it does not
  block them.

**Never claim** that a prompt-injected agent "cannot move funds". What is true:
keys stay local, and on-chain sends are human-gated *on the console edition*.

## Installation and updates

**What holds.** The published skill bootstrap verifies a signed release manifest and the installer hash before executing downloaded code. The installer re-verifies blob/OCI signatures, checks installer/shim hashes and pulls an immutable digest. Trusted cosign 3+ must be installed independently; missing/broken verifier or failed verification refuses installation. A source skill template without its generated bootstrap hash is intentionally not runnable.

`rustok update` verifies a signed release and preserves explicit client capability subsets. Implicit or invalid grants migrate to read-only; ambiguous/unreadable entries are retained and reported. Normal init/restore/start/connect use the locally saved release digest; tags cannot silently change selected bytes. Explicit `RUSTOK_IMAGE` is a visibly unverified development override, rejected by normal update. Host compromise can change local files or steal credentials and remains outside this model.

Live sessions retain their previous image/grants until a human restart. Update never drains or restarts them automatically. The human must stop new requests in all sessions, resolve pending approvals and wait for active execution terminal outcomes before confirming stop. That attestation is not a programmatic quiescence guarantee. Restart loses previews, pending approvals and status outcomes; unknown payment outcomes must be investigated, never automatically replayed. Volumes/keys/policy persist; the password lives separately, so the recovery phrase is essential before uninstall deletes passwords. PIN rotation does not re-encrypt keys; restoring the same phrase does not revoke a leaked key.

No automatic update is promised. Use `--release` to choose a signed version; unsigned legacy versions have no supported verified rollback. Previously published tags/assets are not overwritten.

## Reading the chain

- **A node that reads your balance learns the address and the IP that asked.**
  That is true of every node — the ones this build carries, the one you name, and
  your provider's alike. Since 0.11.0 the wallet carries two public endpoints for
  each chain it shows, so a fresh install reads balances without being configured.
  Naming `RUSTOK_RPC_URLS_<chain>` (or pointing it at a node you run) **replaces**
  the carried list rather than joining it, and an empty value means "read nothing
  on this chain".
- **A public endpoint behind one hostname is a pool of machines, and a lagging one
  answers with state a moment behind.** We paid for that once: a swap simulation
  reported `exceeds allowance` because the machine that answered had not yet seen
  the approval. Transaction numbering does not ride on it — the wallet takes the
  number from its own counter, not from the node.
- **The token shown without being registered is USDC**, listed by contract address.
  On Arbitrum both the native token and the bridged one appear, and the bridged one
  is labelled `USDC.e` **by us**: on chain it calls itself `USDC` too, and only the
  address separates them. A registry you provide replaces this list.

## What we do not verify at all

- **No formal verification, and none planned.** We measured the price on the
  system usually cited for it: roughly 8–11 lines of proof per line of kernel code,
  depending on what you count. A proof lives only while the code is nearly frozen —
  ours changes daily, and much of the product stands on third-party libraries
  nobody will prove. What we took from that world instead is this file.
- **Reproducible builds are observed, not enforced.** Rebuilding a release from the
  same sources has produced the identical image layer, and that is a good sign —
  but nothing in CI asserts it, so do not treat it as a promise.
- **The architecture-edge guard matches text, not syntax.** See
  [`core/docs/ARCHITECTURE-EDGES.md`](https://github.com/rustok-org/core) — it is a
  second line behind the compiler, aimed at drift rather than at someone determined
  to get around it.
- **We take the network's word about the queue number, and bound the damage rather
  than remove it.** Before signing, the wallet asks the node what number its next
  transaction should carry, and it has no way to tell a truthful answer from a
  wrong one — a wallet is usually configured with a single RPC endpoint, so there
  is nothing to compare against. A wrong answer that is too high produces a
  transaction the chain accepts into its pool and never mines, and until 2026-08-17
  the wallet would keep building on that number for the life of the process:
  every later payment reported as sent, none of them arriving, curable only by a
  restart. The wallet now forgets what it remembered after a minute, so it corrects
  itself. Inside that minute the payments still go nowhere. Pick an endpoint you
  have some reason to trust.
- **Scanner findings on our storefront listing are not all ours.** A `Critical`
  currently shown against the skill points at a line that contains no secret; it is
  disputed in [openclaw/clawhub#3381](https://github.com/openclaw/clawhub/issues/3381)
  with an independent scanner's clean result attached. We say this here rather than
  hoping you do not look.
- **One of our own release claims was wrong, and we say so where we made it.** The
  annotation on the `wallet-tui-v0.9.2` tag states an acceptance that had not happened
  when it was written. The correction, with the transaction it should have rested on,
  is in the `[0.9.2]` entry of [`CHANGELOG.md`](../CHANGELOG.md). Same rule as the line
  above: a claim we made in public gets corrected in public.

---

*If you find a boundary we have not named here, that is a bug in this file. Please
open an issue — an unnamed edge is the only kind that is dangerous.*
