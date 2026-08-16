# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **One PIN.** `rustok init` asks you to choose a 6-digit approval PIN and
  generates the keyring password itself; it prints only the 12-word phrase.
  There used to be two secrets — a password you typed and a PIN the wallet
  minted and printed beside the phrase — and the console asked for the second
  while people brought the first (reported live, 2026-08-08). The PIN and the
  phrase reach the wallet over a pipe, never as an argument or a variable, and
  the wallet checks the PIN's shape and refuses the obvious patterns (`000000`,
  `123456`, `121212`, `123123` and their kind) before it writes anything.
  Requires the core that ships with this release; against an older image
  `init` still works and the wallet mints a PIN as before.
- **`rustok init --force` over a live wallet volume now refuses.** It used to
  re-store a password you typed; with the password generated, re-storing would
  make the existing keystore unreadable, so there is no outcome in which the
  command does what it says. Over an orphaned secret (the volume is gone) it
  does what it always did. The refusal names `rustok restore`.
- **The PIN you choose is not as random as the one that was minted — said
  plainly.** The wallet refuses the obvious patterns but not dates; a birthday
  is the one PIN the person next to you already knows, and the console allows
  three tries before a five-minute lockout. CAVEATS says so, INSTALL says pick
  something that is not a date. The keystore itself is under a random 32-byte
  password now rather than a typed one — stronger than before, and the reason a
  guessed PIN opens nothing without it.

### Added
- **`rustok restore`** — bring a wallet back from its 12 (or 24) words onto a
  fresh volume: the phrase on one line, then a new PIN; it prints the address
  it restored so you can check it is the one you expect. Same address, same
  funds; the payment journal and settings do not travel with the words.
- **`rustok set-pin`** — choose a new approval PIN for the running wallet, in
  your own terminal. The old PIN is not needed; the wallet proves it holds the
  keyring password before it changes anything.
- **A guard on the texts.** No published text may describe the two-secret flow
  again — a printed PIN, a typed password, the volume offered as a backup — and
  every text that teaches `rustok init` says you choose the PIN. Same shape as
  the signing guard: it holds the description still and knows nothing about
  what the wallet does; the binary's own tests hold the behaviour.

### Fixed
- **A copy of the wallet volume was described as a backup. It is not.** The
  password that opens it lives outside the volume and, through the shim, is not
  something you know. Every place that said "back up the volume" now says the
  12 words are the backup, and INSTALL carries a table of where each thing
  lives and what protects it.
- **A fast typist could see their PIN.** `stty -echo` came after the prompt, so
  digits typed — or pasted, or fed by a terminal driver — before echo went off
  were shown. Measured under a pty: the PIN appeared twice in the capture. Echo
  now goes off before the prompt. This was true of the old password prompt too;
  the test that would have caught it only looked at the engine's log, not at
  what the shim printed.
- **A refused PIN no longer leaves a half-made wallet behind.** The keystore was
  written before the PIN was read; a PIN the wallet refused left a wallet whose
  phrase had never been shown and whose PIN was never set, and the retry said
  "already exists". The PIN is checked first now, and a refusal leaves the data
  dir empty. On the shim's side, the secret it had just stored is removed on a
  refusal too, so the retry does not run into "secret already exists".

## [0.9.8] — 2026-08-12

### Fixed
- **`sign_message` is refused outright, and the texts finally say so.** Core
  policy denies it in every mode, autonomous included, and has since v0.4.0 —
  `(_, SignMessage | SignTypedData) => Decision::Deny`. Ten published places said
  it returns a signature without console approval, describing a hole that is
  closed. It is neither a hole nor a protection: signature parking (`kind:sign`)
  is planned and not built.

  Live acceptance of 0.9.7 caught it. A spec, a self-check and three review
  rounds had not, because each of us read our own earlier documents instead of
  asking the wallet.

### Added
- **A two-part guard against the same class.** One half asks the shipped image
  (pinned by digest, since that is the bytes a user runs) and never reads a text;
  the other requires the true sentence in every text that names the tool and
  cannot tell true from false. The live half runs as its own CI job, with podman
  verified present first: a guard that is silently not selected reports the same
  green as one that ran.
- **`docs/CAVEATS.md` states that a parked transaction lives exactly as long as
  the wallet session.** Close the session while something waits and the parked
  item is gone. Nothing said this anywhere; it was found by losing one.

### Changed
- `docs/INSTALL.md` no longer promises a 150-line installer that is 321 lines —
  the rot fixed in SKILL.md last release had survived in the page people actually
  install from, because the guard read one file instead of the class. It is now
  parametrised over both.

## [0.9.7] — 2026-08-12

### Added
- **The wallet states what it does not promise.** A `## Legal` section in the
  skill and a full [DISCLAIMER](DISCLAIMER.md) that names the limit of every
  safeguard, including the two easiest to read as absolute: autonomous mode
  sends without asking once a human has confirmed it, and `sign_message` is
  refused outright in every mode — signature parking is planned, not built.

  The first published wording of that second limit was wrong in the other
  direction: it described a hole that is closed. Live acceptance of 0.9.7 caught
  it, and 0.9.8 corrects every text that said it.

  The published texts already disclaimed warranty (MIT-0 "as is") and warned
  that funds are at risk. What none of them said was that the agent is
  third-party software whose output is unpredictable, and that a transaction it
  proposes is not an act of the authors.

### Fixed
- **The rot guard shipped in 0.9.5 read line by line**, so the very phrase it
  was built to catch slipped past it when that phrase wrapped across two lines —
  which is how it appeared in the file it was written for. It now matches the
  whitespace between the words and keeps the exact line number.

### Withdrawn
- **0.9.6 was tagged and withdrawn — do not install from `wallet-tui-v0.9.6`.**
  The tag was cut before the image digest was pinned, so its `install.sh` carries
  the 0.9.5 digest under a 0.9.6 label. That does not fail: the installer pulls
  by digest, the 0.9.5 image is present and validly signed, so the install
  completes, reports 0.9.6, and leaves a shim that runs the 0.9.6 tag — the image
  verified at install is not the image that runs. Our own policy never moves a
  published tag, and a repository ruleset enforces it, so the release was reissued
  as 0.9.7 instead. Content of 0.9.6 and 0.9.7 is otherwise identical.

## [0.9.5] — 2026-08-12

### Fixed
- **Gas limits now carry headroom** (core 0.4.3). A limit set to exactly the
  estimate turned any drift between estimating and executing into a burnt fee —
  a contract call could pay its gas and do nothing. Plain transfers were never
  affected.
- **`rustok connect --force` names what it is about to drop** instead of quietly
  rebuilding the registration from the current shell.

### Changed
- **ERC-20 token registration is documented in the skill at last.** The wallet
  has been able to report registered tokens since 0.9.4, but the published skill
  never said so, and an unregistered token reads exactly like an absent one.
- **`executed` is now stated to mean broadcast, not succeeded.** A transaction
  that reverts on-chain still reports `executed`; the receipt is what settles it.

## [0.9.4] — 2026-08-11

### Added
- **The wallet can see the tokens it is allowed to hold.** Until now it could
  send USDC but never show it: balances were the chain's native coin and nothing
  else, so a wallet holding 22.82 USDC reported an empty Arbitrum balance and an
  agent reading it concluded there was nothing there.

  Register what you hold — `RUSTOK_TOKENS_42161=USDC:0xaf88…5831:6` — and the
  token appears everywhere a balance does: in `get_balances`, in
  `get_wallet_context`, and on the console's balance panel. The registry is
  explicit on purpose: the wallet shows what you told it about, it does not go
  hunting for tokens on your behalf.

  A row now carries the asset's own `decimals`, the rendered
  `balance_formatted`, and the `token_address` that tells native USDC from
  bridged USDC.e — a symbol alone cannot, and both live on Arbitrum.

  **An asset that could not be read is now said out loud.** A chain with no RPC
  used to contribute no row, which read as "you have nothing"; `unavailable` now
  names the asset and why — no RPC configured, the call failed, or the call
  reverted, which means the address in your registry is not the ERC-20 it was
  said to be.

### Changed
- **`balance_eth` stopped being arithmetic.** It is now an alias of
  `balance_formatted` on the native row, and it is **absent from a token row**:
  USDC has six decimals, not eighteen, and a field with `eth` in its name would
  state a unit the number is not in. Existing readers of the native row see the
  same name and the same value as before. Use `balance_formatted` for any asset.

  One place still converts wei, and only one: `get_balances{address, chain_id}`
  for an explicit address, where the core answers with raw wei and renders
  nothing. That path is native by construction — the registry describes your
  wallet, not somebody else's address.

- **Closing the console puts away what it took out, and says what it did.** `q`
  used to leave two things behind: a wallet still running, and no word about what
  had just happened. The screen is cleared, one line states the outcome, and a
  wallet this console started is stopped again.

  A wallet that was *already* running is left alone. Stopping it would kill the
  process an agent is mid-turn with, and an approval parked there lives in that
  process's memory — the person would destroy the very thing they opened the
  console to confirm.

  Closing the terminal window abruptly is still not the same as quitting: the
  shim is killed before it can tidy up. `rustok stop` remains the way back.

## [0.9.3] — 2026-08-09

### Added
- **The console answers "what am I actually running".** The identity panel used
  to show one number — the console's own — which does not move between wallet
  releases. Someone who installed 0.9.2 opened it, read `console v0.3.0`, and
  reasonably concluded the update had not happened.

  It now names every layer:

  ```
  RUSTOK WALLET
  wallet   v0.9.3
  console  v0.3.1
  core     v0.4.1
  ```

  This is diagnosis, not decoration. In one day of release work there were three
  separate moments when nobody could answer that question from the screen: an
  agent silently running a wallet four versions old, a send believed to be on the
  published image that was not, and the panel misread as a failed update. All
  three were visible in a container inspection and in none of the places a person
  actually looks.

  Outside the wallet image — the console run on its own — the panel prints
  exactly what it printed before: one line, for the binary that knows itself. A
  layer that says nothing gets no row, never the word `unknown`. Absence is not
  a value.

### Changed
- Console pinned to `v0.3.1`.
- The image now states its own version and the core's, and refuses to be built
  if the core version it would state disagrees with the core image it is built
  from. The wallet's number comes from the same input the publish workflow
  already checks against `pyproject.toml`, so the panel and the manifest cannot
  part company.

## [0.9.2] — 2026-08-08

### Fixed
- **Payments could be refused by the network, and 0.9.0 and 0.9.1 shipped that.**
  Every transaction was built as a legacy one. The fee headroom — the margin that
  absorbs a base fee rising between the moment a transaction is built and the
  moment a block includes it — was written, unit-tested, and never reached: it
  lives in the EIP-1559 branch of the pipeline, and nothing in production ever
  selected that branch. A send priced at the gas price the node quoted is refused
  the instant the base fee ticks up, with `max fee per gas less than block base
  fee`. Measured on a real wallet: four refusals.

  Transactions are EIP-1559 by default now, and the legacy path carries the same
  headroom. Verified on chain rather than only in the suite: a send on Arbitrum
  went out as `type 0x2` with a `maxFeePerGas` of 40060000 while the effective
  gas price at inclusion was 20118000 — the base fee had risen 0.44% since the
  transaction was built, so without the headroom that very send would have been
  refused.

- **A refused send said nothing about why.** The node's own reason now reaches
  the operator, through a closed list of six known refusals; every other failure
  stays masked exactly as before.

- **`create-wallet` let you believe the PIN was your keyring password.** It now
  names which one it is asking for.

### Changed
- Core pinned to `v0.4.1`.

  Worth upgrading if you send anything: 0.9.0 and 0.9.1 can have a payment
  refused on a rising base fee. Nothing updates on its own — the installer pins
  an exact digest.

### Erratum — added 2026-08-09

The annotation on the `wallet-tui-v0.9.2` tag says this release was accepted on
the published image. That was not true when it was written. The Arbitrum send
quoted above was made from a local build of this same commit, not from the
published artifact — the claim was true of the code and false of the thing you
download, and telling those two apart is the entire reason this project pins a
digest.

Acceptance on the published image was completed afterwards, on
`ghcr.io/rustok-org/rustok-wallet-tui@sha256:996f81a0`: transaction
`0xb20a32f1e1d078f95bf5743b16b41a18bcb522298f9e2fd064bb2b0578d3012c` on
Arbitrum, block 492644798, `type 0x2`, `status 0x1`, carrying a `maxFeePerGas`
of 40020000 and included at an effective 20014000. Both numbers are on chain,
and together they show the headroom doing its job: the ceiling is twice what
the node quoted when the transaction was built, so the quote was 20010000 —
below the 20014000 the block actually charged. Without the headroom the ceiling
would have been the quote itself and this send would have been refused.

The two sends made while testing the fix stand on chain the same way, and the
same arithmetic applies to both:
`0x053c917aad0c4e1a42bde84c70f8c71dbd193c4d351e03b7a5ef0a43462dcafa` in block
492454482, ceiling 40060000 against an effective 20118000, and
`0xced4b99f4b5c9a4784b0b205cd261327df8cd9659170fc999d613092fdf0e8ae` in block
492636459, ceiling 40016000 against 20026000. Three sends, and in all three the
base fee had risen past the quote by the time a block took the transaction —
which is why the bug this release fixes was a systematic refusal rather than an
occasional one. Every number here can be checked without taking our word for
it, which is the point of writing it down this way.

The tag itself is left alone. It points at the right commit, and moving a tag
that others may already have fetched would trade one wrong claim for a worse
one. This note is the correction, and it is here rather than in an internal
record because the claim it corrects is public.

## [0.9.1] — 2026-08-08

### Fixed
- **The wallet said it could not send on its own. It could.** 0.9.0 gave the
  wallet the ability to execute a payment once a human confirmed autonomous mode
  at the console — and six texts kept describing the old, unconditional gate.
  Three of them are read by the agent: the `execute_transaction` tool
  description, the standing server instruction, and the tool table in the skill
  card. An agent told the wallet cannot send by itself does not warn the human
  and does not treat a send as final.

  Every one of those texts now states all three cases in the same breath: a
  supervised wallet parks the payment; an autonomous wallet whose owner has not
  yet confirmed the mode parks it the same way; an autonomous wallet whose owner
  confirmed it releases without asking again. `policy_mode` and `policy_origin`
  from `get_wallet_context` say which case you are in.

  None of these files changed in 0.9.0 — they became false without being
  touched, which is why a review that reads a diff did not see them. A guard now
  fails if any of those texts describes the gate without admitting the mode.

- **The listing description said sending "requires your approval".** It now says
  the gate is in the console and names both ways through it.

## [0.9.0] — 2026-08-08

### Added
- **Autonomous mode sends for real — after you confirm it once.** Until now
  `autonomous` was a mode the wallet could be in and still parked every payment.
  It now executes, on one condition: a human has confirmed that mode on this
  wallet. Open the console, press **`c`**, enter your PIN — once per wallet.

  The confirmation is asked for in the console and nowhere else. It cannot be
  given by the agent, by an environment variable, or by a launch flag.

- **The console says which mode this wallet is in, on every screen.** The mode
  and whether it is confirmed are one statement, because either half alone
  misleads: an `autonomous` wallet nobody has confirmed still parks everything.
  Unconfirmed autonomy is the one state drawn as a warning — it is the one where
  what you expect and what the wallet does come apart.

- **The audit log records who released a payment** — you at the console, or the
  wallet acting on autonomy you confirmed — and which payment it was. Before
  this, a human approval left no row of its own, so after an incident the two
  could not be told apart.

### Changed
- **If your wallet is in autonomous mode and you have not confirmed it, the
  first send after this update will park and wait for you.** This is deliberate
  and it is the part worth reading twice.

  Wallets created by the pre-console line have a keystore and no PIN record, and
  that is exactly what the core reads as "autonomous". Such a wallet has never
  had an approval gate in front of it. Turning on autonomous execution for it
  silently would mean money moving out of a wallet that was never asked. So it
  parks once, the console shows a banner saying so, and one confirmation clears
  it for good.

  Confirming does **not** release payments already in the queue. While the mode
  was unconfirmed an agent may have retried, so the queue can hold duplicates of
  one payment under different nonces; they stay for you to decide one by one.

  Confirmation from a messenger is not in this release. It is the next one.

## [0.8.5] — 2026-08-06

### Added
- **`rustok connect openclaw`.** OpenClaw was unsupported, so the first
  third-party agent to install this wallet had to route around us: generate the
  command with `rustok connect claude`, then register it in OpenClaw by hand.
  The client is now first-class across the whole lifecycle — `connect`, `update`,
  `uninstall` and `doctor` — not just in the dispatcher, so `rustok update` no
  longer walks past a registration it cannot see.

  Registration goes through OpenClaw's own CLI (`openclaw mcp set`), which
  **replaces** an entry in a single call: unlike the `claude` path there is no
  remove→add window in which the wallet is registered nowhere. `openclaw mcp
  reload` follows the write, so a session already open stops serving the cached
  command instead of failing on the next turn; a failed reload warns rather than
  failing the registration that has already landed.

  One thing worth knowing before you uninstall: OpenClaw refuses a config write
  made through its own CLI when the file shrinks too far — its message carries
  the token `size-drop`, and `openclaw config unset` hits the same guard.
  `rustok uninstall` relays OpenClaw's own words and the recovery that was
  measured end to end: `openclaw doctor --fix` (it writes the defaults back and
  raises the size the guard compares against), then repeat `openclaw mcp unset
  rustok`. Editing the config outside OpenClaw is not gated and also works; it
  only earns a one-line `Config observe anomaly` notice afterwards.

### Removed
- **The donation ask is gone from everything an agent reads.** The server's
  `initialize` instructions and the published skill both asked the model to
  raise the subject of supporting this project — with an address and suggested
  amounts — with the human it works for. An agent meeting the wallet for the
  first time flagged it unprompted, as something baked into the tool rather than
  what its human had asked for. A product trusted with keys does not lobby the
  agent on its author's behalf. The ask lives on the website, where a human
  chooses to read it.

### Fixed
- **A skipped signature check now says so where it gets read.** When `cosign` is
  unavailable the installer has always announced the skip — in the middle of a
  long install log, where it scrolls away. The first third party to install this
  wallet did not notice, and worked out from the outside that provenance had
  never been checked. The closing summary now repeats it and names the version
  requirement where it is actionable: the check needs **cosign 3 or newer**,
  because our signatures are OCI referrers that 2.x cannot see at all. Nothing
  about the install changes — the image is still pulled by digest, and a
  signature that is present but does not verify still stops everything.
- **The console command the wallet prints now works.** `initialize`, the
  `next_step` of every parked transaction and the `execute_transaction`
  description all told the human to run
  `docker exec -it rustok-wallet-tui rustok-console`. There is no container by
  that name — the wallet is launched by label, on purpose — so the command
  failed for anyone who installed the documented way, and it named `docker` on a
  product that recommends `podman`. All three now name `rustok console` first
  and the label-discovery form second, with the engine left to the reader. The
  grep-invariant that has guarded this exact papercut since July covered only
  the docs; it covers the source and its tests now, which is why it stayed green
  while the defect shipped.


## [0.8.4] — 2026-08-04

> Written after the fact (2026-08-06): 0.8.2, 0.8.3 and 0.8.4 all shipped
> while their notes sat in `[Unreleased]`, so the entries below were
> reconstructed from the commits between `wallet-tui-v0.8.3` and
> `wallet-tui-v0.8.4`. The releases themselves are unchanged.

### Security

- **The gateway API key is delivered as a path, not a value.**
  `resolve_outbound_api_key` reads `RUSTOK_MCP_API_KEY_FILE` when set and
  falls back to the plain variable; the entrypoint stages the key under
  `/run/wallet` at `umask 077`, unsets the value and exports only the path,
  so it is in no process's environment. An unreadable or empty file is fatal
  at startup instead of a silent "no key". Companion to `core#105`, which
  moves the capability ceiling onto the gateway's request path.

### Added

- **`docs/CAVEATS.md` — one place for what this wallet does not guarantee.**
  The same boundary had been written from scratch four times in a single day
  (release notes, `INSTALL.md`, `CONFIGURATION.md`, an audit dispute), each
  slightly differently scoped — which is how a boundary quietly becomes a
  claim. `INSTALL.md` and the skill link to it instead of restating a subset.

## [0.8.3] — 2026-08-03

### Security
- **The keyring password no longer lives in any process's environment.**
  Until now every process in the wallet image — core, the gateway and the MCP
  server — carried it in `/proc/<pid>/environ`, where anything running as the
  same user could read it, decrypt `keystore.json` directly and re-mint the
  approval PIN. Reading `/proc/*/environ` is the cheapest secret harvest there
  is, and it made the console edition's PIN gate bypassable. Only the core ever
  needed the password; the other two held it because the entrypoint exported it.

  Now the password reaches the core as a *file*, and only as a file. Supplied
  the documented way (a mounted secret plus `RUSTOK_KEYRING_PASSWORD_FILE`), it
  is in no environment at all and `podman inspect` carries a path instead of the
  value. Supplied the compatibility way (`-e RUSTOK_KEYRING_PASSWORD`), the
  entrypoint stages it in a 0600 file, drops the variable, and removes the file
  once the core has unlocked — and because the entrypoint is now PID 1 and hands
  that role to `tini` through `exec`, even PID 1's own environment is rewritten.
  A file *you* mounted is never deleted.

  **What this does not cover, stated plainly:** with `-e` delivery the value
  still sits in the container config (`podman inspect`) and, under `--init`, in
  the runtime's own PID 1 — neither is reachable from inside the image, which is
  why the file delivery is the documented one. Nothing here defends against code
  already running as the same user: it can read the staged file during its short
  life, the core's memory, and the data volume. Measured on podman 5.8.4; docker
  is not installed on the machine these runs were made on, so its behaviour is
  expected to match by mechanism but is **not verified**.

- **`rustok init`/`start`/`connect` now deliver the password as a mounted
  secret**, not `--secret …,type=env`. The generated command was the leaky path
  itself: documentation alone would have fixed the advice and not the product.
  Existing registrations keep working; re-run `rustok connect <client>` to move
  an already-registered client onto the new command.

- **Secret files on disk are owner-only** (core `v0.3.1`). `keystore.json` and
  `approval-pin.json` were world-readable (0644) — they are now written 0600 and
  narrowed on the first start of an existing wallet, which says so in the log.

### Changed
- **`--init` is gone from every documented command.** The entrypoint is PID 1
  itself and hands the role to `tini` through `exec`, so signal forwarding and
  zombie reaping are covered without it; with `-e` delivery an extra init
  process is a carrier nothing inside the image can clear.
- The image is built on core `v0.3.1` (from `v0.3.0`).
- **`sign_message` schema matches its documented contract.** The `sign_type`
  enum listed `eip712` while the tool description said EIP-712 is not
  supported; the enum is now `["eip191"]`.

### Fixed
- **A client can no longer expand its own capabilities via `initialize`.**
  The rustok capability list now *intersects* with the transport-seeded
  ceiling instead of replacing it: an operator launching the wallet with
  `RUSTOK_MCP_CAPABILITIES=read_wallet` gets a session the agent cannot talk
  out of (audit B1). With no seeded ceiling the granted set fails closed to
  empty — the server seeds, the client only narrows. The same env ceiling
  now also seeds SSE sessions (they keep the gated-until-granted contract
  only when it is unset).
- **The capability ceiling now also follows the wallet core's policy mode.**
  `initialize` reads `policy_mode` from the core (via WalletContext, core
  increment 1): `read_only` leaves read + preview tools, `supervised` /
  `autonomous` keep the full set while the core itself parks or denies
  writes. When the core is unreachable the transport ceiling applies alone,
  with a warning — MCP-side filtering is advisory; enforcement lives in the
  core.
- **A second `initialize` on the same SSE session can no longer change its
  capabilities.** The guard was the falsy empty set, so a standard MCP
  capabilities *object* (which parses to empty) left the session open to a
  second, wider grant. The session now tracks `initialized` explicitly.


## [0.8.2] — 2026-07-22

> Written after the fact (2026-08-06), reconstructed from the commits between
> `wallet-tui-v0.8.1` and `wallet-tui-v0.8.2`. Nothing about the release itself
> changed.

### Fixed

- **`uninstall --purge-keys` gated the keys after tearing everything down.**
  Run through a pipe or an agent it refused correctly — but only after
  deregistering the clients, stopping the wallets, deleting the secrets,
  removing the PATH block, deleting the shim itself and wiping the config
  directory. The keys survived; the installation did not, and the user was
  left without the command that manages them. A gate that fires after the
  damage is not a gate.
- **The installer stopped asserting things it does not do.** A first-user
  probe and a read-only audit of `install.sh` found the same class of defect
  underneath a working install: statements about its own behaviour that were
  not true. Nothing here broke an installation; all of it misinformed the
  person running one.
- **The ClawHub listing still sold cosign as a prerequisite.** `SKILL.md` is
  the listing — the text a new user reads first and copies commands from —
  and it still named cosign as required, which is the exact wall 0.8.1 exists
  to remove.

## [0.8.1] — 2026-07-22

### Fixed
- **cosign is no longer a hard prerequisite of the one-command install.** The
  first live install hit a wall the release had not anticipated: `install.sh`
  refused to run without `cosign`, which Fedora does not carry in its
  repositories — so "one command" became "first go and find a verification tool
  somewhere". Integrity never depended on it: the image is pulled **by digest**
  (content-addressed — those bytes or nothing) and the script itself ships from
  an immutable tag. cosign proves *provenance* (built by this repo's workflow),
  which is a layer worth having and a poor gate. The installer now branches
  three ways, and never silently: cosign missing **or unable to run** → warns,
  names the digest, prints the command to check provenance later, and continues;
  cosign works and the signature verifies → says so and continues; cosign works
  and the signature does **not** verify → still refuses, fail-closed.
- **A broken cosign is no longer reported as a tampered image.** Branching on
  `command -v` answered "is there a file called cosign", not "can it run" — and
  answered it differently per shell (for a present-but-non-executable file
  `/bin/sh` says no, `bash` says yes). A cosign that exists but cannot execute
  (no `+x`, wrong architecture, missing libc, truncated download) therefore
  reached `cosign verify`, whose non-zero exit is indistinguishable from a bad
  signature, and the user was told their image was tampered with. The installer
  now probes with `cosign version` first and treats "cannot run" as "no cosign".
- **The refusal message stopped over-claiming.** Keyless verification reaches the
  Sigstore transparency log over the network, so a failed check may equally mean
  no connectivity, a rate limit or an outdated cosign. The message now names both
  possibilities instead of announcing sabotage; the behaviour stays fail-closed.

### Changed
- `docs/INSTALL.md` and `docs/TROUBLESHOOTING.md` describe cosign as an optional
  provenance layer rather than a requirement, and spell out what the digest
  guarantees without it. Platform support is stated honestly: `linux/amd64`,
  Windows via WSL2, no native Windows installer, macOS/arm64 not published.

## [0.8.0] — 2026-07-21

### Added
- **`rustok` — the shim (`cli/rustok`).** The wallet is now driven by one
  command instead of a page of container invocations: `init` (creates the
  wallet, prints the 12-word phrase and the approval PIN exactly once, and
  **refuses to run without your own terminal** so neither can leak into an
  agent's context), `connect claude|cursor|hermes` (registers the wallet as an
  MCP server with that client), `console` (the approval window — starts the
  wallet if it is not running), `start`/`stop`/`status`/`doctor`, `update` and
  `uninstall`. Wallets are discovered by label (`rustok=wallet` +
  `rustok.agent=<name>`), never by a fixed `--name`, and every agent gets its
  own keystore volume; two wallets running without `--agent` is a named refusal
  listing them, never a silent first match.
- **Keyring password can arrive as a file** — the wallet image honours the
  `RUSTOK_KEYRING_PASSWORD_FILE` convention (`podman secret …,type=mount` or a
  bind-mounted `0600` file), with named errors for a missing, non-regular or
  empty file instead of hanging on an absent password. **This needs image
  `0.8.0`+**: the previously published `v0.7.1` was built before this support
  landed, so docker's `_FILE` delivery does not work against it.
- **The wallet image is signed in CI** (keyless cosign in `wallet-publish`),
  which is what gives the installer something to verify.
- **Per-chain RPC secrets** — `connect` stores every `RUSTOK_RPC_URLS_<chain>`
  as a podman secret `rustok-rpc-<agent>-<chain>` (atomic
  `secret create --replace`; `secret rm` is banned — it succeeds silently even
  on a held secret) and both the registration and `rustok start` deliver the URL
  through that secret, so a keyed RPC URL stays out of argv, out of the agent's
  config and out of `inspect`. Docker fallback keeps the honest literal `-e`
  (documented second tier).
- **`scripts/install.sh`** — one-command installer (`curl … | sh`), a full
  rewrite of the old command-printer. It installs the `rustok` SHIM, not the
  wallet: verifies the wallet image's cosign signature against this repo's
  publishing workflow FIRST (fail-closed — nothing lands on disk until the
  image is proven), pulls it BY DIGEST (a mutable tag cannot be swapped in),
  fetches the shim from a COMMIT-SHA-pinned raw URL over `--proto '=https'
  --tlsv1.2`, installs it to `~/.local/bin` and adds the 2.3c-contract PATH
  block (`RUSTOK_NO_MODIFY_PATH` opts out; idempotent). It NEVER touches a
  secret, keystore or wallet init — creating the wallet stays a human step
  (`rustok init`) run in your own terminal, never through the pipe. The
  release-pinned digest and shim commit start as fail-closed placeholders,
  filled at release time. Hermetic test suite (stub curl/engine/cosign, no
  network) + a new CI job.

### Changed
- **`rustok update`** — pulls the current wallet image FIRST (a broken pull
  stops the run before any config is touched), then re-registers every
  rustok MCP entry across claude/cursor/hermes. Each client keeps its own
  wallet: the agent is read back out of the entry's own `rustok.agent`
  label (self-healing — no side-car state to go stale) and passes the same
  charset gate as `--agent`. The replaced entry is printed per client; a
  running wallet keeps the old image until its agent's next session start.
  The shim itself does not self-update — re-run the installer.
- **`rustok uninstall`** — data-safe teardown in reverse install order:
  deregisters from all three clients (foreign config keys untouched;
  hermes gets a timestamped backup), stops running wallets, removes the
  `rustok-keyring-*`/`rustok-rpc-*` secrets (or the docker password
  files), removes the installer's marked PATH block (`# >>> rustok
  installer >>>` … `# <<< rustok installer <<<` — the 3.2 contract; no
  markers, no touching a shell profile; a profile with duplicate markers
  is left untouched with a named warning, never blind-deleted) and
  `~/.local/bin/rustok`. **Keystore volumes are NEVER touched** without
  `--purge-keys` AND its interactive `delete my keys` confirmation read
  from /dev/tty (a pipe or blind automation gets a named refusal) — the
  one gated road through the shim to the keys.
- **Old-entry print on every replace** — the claude writer now prints the
  previous entry on a successful `--force` replace too (it used to print
  only when the re-add failed), and the hermes writer prints the replaced
  `rustok` block before writing (it used to rely on the backup file
  alone): one recovery path across all three writers, so a routine
  `update` can never swallow a hand-tuned entry silently.
- **`rustok connect cursor` / `rustok connect hermes`** — the remaining two
  clients get the one-command registration. Cursor: a jq write into
  `~/.cursor/mcp.json` (no registrar CLI exists; atomic tmp+mv, the old
  entry printed back as the return path). Hermes: a python3+PyYAML
  round-trip into `~/.hermes/config.yaml` (`mcp_servers.rustok` with
  `enabled: true` and a REAL args list; backup + atomic write) that also
  replaces the Stage-0-era `rustok-wallet` entry (the args-as-JSON-string
  bug) and hints at removing the obsolete wrapper script. The wallet
  defaults to the client's own (`--agent` overrides) — every agent gets
  its own keystore.
- **`rustok connect claude`** — one-command MCP registration: builds the
  `claude mcp add -s user rustok` invocation (both labels, per-agent volume,
  keyring secret, RPC secrets, frozen `-e` config, image), with named
  refusals for every broken precondition (no init, env-file-era volume →
  migration path, already registered without `--force`, broken agent
  config JSON, missing jq) and a volume-domain warning when containers
  already share the keystore.
- Registration existence is probed by reading `$HOME/.claude.json` (jq,
  read-only; user-scope only) — never `claude mcp get`/`list`, which
  health-check and thereby start a wallet container on the shared keystore.
- **The keyring password is delivered by secret or file, never inline.** Inline
  `-e` values, environment passthrough and `--env-file` are retired to a legacy
  note: the value is visible in `inspect` (and, for an env block, in the MCP
  config), and inside an env-file **quotes become part of the password** — a
  silent unlock failure that broke a real onboarding.
- **Documentation is written around the one-command install**; the by-hand
  container setup survives as an explicit appendix for anyone who will not pipe
  a script into a shell. `rustok update`'s limits are stated wherever it appears:
  it pulls by tag and does not re-run the cosign verification.

### Removed
- **`skills/rustok-wallet-tui/scripts/health-check.sh`** — an unreferenced
  leftover that taught an inline password in its header and forwarded one through
  the environment in its body. `rustok doctor` / `rustok status` do its job
  safely.

### Fixed
- **Fixed container names collided.** The agent launches the wallet itself, so a
  hard-coded `--name` failed the moment anything started a second instance (a
  health probe, an `mcp list`) — and with `--replace` it would kill a live
  wallet. Discovery is by label now.
- **Hermes could not see its wallet.** A wrapper script broke the protocol (zero
  tools). Hermes gets its own volume and sub-label, written by
  `rustok connect hermes`; the obsolete wrapper is called out for removal.
- **The MCP entry name in the docs did not match the code.** Examples registered
  `rustok-wallet-tui` while the shim writes — and looks for — `rustok`, so a
  hand-built setup was invisible to `update` and `uninstall`. The shim already
  warned about this "doc-era" entry; the docs were its source.

## [0.7.1] — 2026-07-15

### Fixed
- **MCP protocol version negotiation** — `initialize` now mirrors a supported
  client revision (2024-11-05 … 2025-11-25) instead of a hard-pinned
  2024-11-05, which current Claude Code silently rejects (30 s timeout, no
  wallet). Found by the first real user on day one.
- **JSON-RPC responses carry `result` XOR `error`** — every response used to
  ship `"error": null` next to its result (and vice versa), which a strict
  client parser (Claude Code 2.1) rejects as malformed; one serialization
  seam (`JsonRpcResponse.to_wire`) now emits exactly one of the two keys on
  both transports (stdio, SSE). This was the second, decisive half of the
  same connect failure.
- **serverInfo/OpenAPI/__version__ read the package metadata** — three
  hardcoded version strings could drift from the shipped version (the v0.7.0
  image reported 0.6.0).

## [0.7.0] — 2026-07-15

### Changed
- **Wallet image ships the resident console** (`rustok-console:v0.2.0`) on the
  first proto-2 core (`rustok-core:v0.3.0`): PIN-unlock opens a dashboard
  (balances, DeFi positions, "waiting for you"), decisions raise notices on a
  LIVING console instead of ending the process, Receive shows the address with
  a QR, Activity keeps a decision journal that outlives the core's retention
  window. Machine callers read one JSON line per decision from a non-TTY
  stdout; exit codes now report only how the session ended.
- **The e2e acceptance asserts the resident model**: outcome notices + the
  agent-side status (two layers of the same truth), the console surviving every
  decision, and `q` -> exit 6 as the only everyday way out. The v0.1
  per-decision exit codes (0/4, failed=1) and the "Pending approvals" screen
  no longer exist and are gone from the suite.

### Added
- **End-to-end acceptance suite** (`tests/e2e`, marker `e2e`): drives the shipped
  `rustok-wallet-tui` image through the real approval channel — the agent proposes over
  MCP stdio, a human decides in a pty-driven console, the core signs and broadcasts to a
  local anvil. Covers approve/deny/expiry/PIN-lockout/unlimited-approve/no-tty/no-auth.
  Not part of the default run (it needs podman): `uv run pytest -m e2e`.

### Documentation
- **Upgrading the wallet image** (INSTALL, TROUBLESHOOTING): the wallet lives in the
  volume, not the image; the pending approval queue does not survive a restart.

## [0.6.0] — 2026-07-11

### Added
- **`execute_transaction` tool** (capability `execute_tx`): parks a previewed
  transaction for human approval — the wallet never sends it on its own. A
  `pending` result carries a `next_step` hint pointing the human at the approval
  console (`docker exec -it rustok-wallet-tui rustok-console`).
- **`get_execution_status` tool** (capability `execute_tx`): polls a parked
  execution — `pending` / `executed` (+`tx_hash`) / `denied` / `expired` /
  `failed` (+`error_reason`), with the `not_after_unix` approval deadline.
- Gateway 404 `not_found` (unknown or expired `preview_id`) now reaches the
  agent as machine-readable `ERR_NOT_FOUND` (-32014) instead of a masked
  internal error, so status polling knows when to stop.
- `Dockerfile.wallet` carries `org.opencontainers.image.source` so GHCR links
  the package to this repository.

### Changed
- Version unified to **0.6.0** across manifests, docs, and image tags.

## [0.5.0] — 2026-07-10

### Renamed
- **The console-gated wallet is now its own product: `rustok-wallet-tui`**
  (image `ghcr.io/rustok-org/rustok-wallet-tui`, skill `skills/rustok-wallet-tui/`,
  container/volume `rustok-wallet-tui`). Renamed before announcement — the 0.5.0
  release had no consumers under the old name. `rustok-wallet` remains the
  unrestricted agent edition (0.4.x line: site, ClawHub, MCP Registry, `latest`).

### Added
- Wallet image now ships the human-approval console (`rustok-console:v0.1.0`) as
  `/usr/local/bin/rustok-console`.
- Onboarding prints both the 12-word recovery phrase and the 6-digit approval PIN.
- Two-window rule documented: human approvals happen in `docker exec -it
  rustok-wallet-tui rustok-console`, never inside the agent chat.

### Changed
- Wallet image version unified to **0.5.0** (`pyproject.toml`, `server.json`,
  `claw.json`, `SKILL.md`, `smithery.yaml`, docs).
- Core base image updated to `rustok-core:v0.2.0` (first core release with the
  approver socket + PIN + core-executes-on-approve).
- All `docker run` examples use the fixed container name `--name rustok-wallet-tui`
  (singleton) and explicit `v0.5.0` tag instead of `latest`.
- Mnemonic references across docs updated from 24 words to 12 words (org
  standard).
- `Dockerfile.wallet` pre-creates `/run/wallet` and `entrypoint.sh` recreates it
  on startup for podman tmpfs compatibility.

## Package reset — v1 (Rust) → v2 (Python)

> **Package reset:** the MCP server was rewritten from the v1 Rust binary
> `rustok-agent-mcp` (AGPL, ≤ 0.2.2) to a Python package **`rustok-mcp`** and the
> version line was reset to **0.1.0** (see `pyproject.toml`). The `[0.2.2]`,
> `[0.2.1]` and `[0.1.0]` entries below are **superseded v1 (Rust) history**, kept
> for the record.

### Added
- Distribution repository scaffold: install scripts, Docker, docs
- `get_wallet_context` and `get_balances` tools wired to Gateway REST
  (`GET /api/v1/wallet/context`) — stubs removed (PR-3.5)
- Optional `chain_id` filter argument for `get_balances`
- `RUSTOK_MCP_HOST` setting (default `127.0.0.1`; set `0.0.0.0` in Docker)

### Changed
- Server/image version unified to **0.3.2** (was 0.1.0) to match the ClawHub
  skill — `pyproject`, the FastAPI app, and the MCP `serverInfo` clients see at
  `initialize` now all report 0.3.2. Added `server.json` for the official MCP
  registry (OCI/stdio package) plus the required
  `io.modelcontextprotocol.server.name` image label in `Dockerfile.wallet`.
- Dockerfile rewritten for the Python server (uv multi-stage build,
  non-root runtime, SSE entrypoint); legacy Rust-binary image removed
- `get_balances` accepts optional `address` (+ required `chain_id`) and then
  queries `GET /api/v1/wallet/balance` instead of the wallet context
- 4xx Gateway errors: only the `message` field of the known error shape is
  forwarded; unrecognized bodies (e.g. dev stack traces) are logged and masked
- `.dockerignore` updated for the Python layout (`.venv`, `__pycache__`,
  caches, tests); legacy Rust patterns dropped
- `get_positions` tool (Aave v3 + ERC-4626) gated by `read_wallet`, backed by
  Gateway `GET /api/v1/wallet/positions`
- **Self-custody all-in-one image** `ghcr.io/rustok-org/rustok-wallet`
  (`Dockerfile.wallet`): runs Core + Gateway + MCP in one container and speaks
  MCP over **stdio** — keys stay in the user's local volume. One-time onboarding
  via `… create-wallet` (prints the 24-word recovery phrase once). Published by
  `.github/workflows/wallet-publish.yml` on version tags.
- The `rustok-wallet` skill (`skills/rustok-wallet/`) + `smithery.yaml` rewritten
  for the stdio Docker command (works on ClawHub, Smithery, Claude Desktop).

> **Migration (v1 → v2):** the wallet is now a Docker image run over stdio, not a
> single native binary. Existing v1 ClawHub installs keep working until you
> migrate: pull `rustok-wallet`, run `create-wallet`, and update your MCP config
> to the new `docker run -i` command (see `docs/INSTALL.md`).

### Removed
- v1 Rust-binary distribution: the fake-binary `release.yml` workflow, the
  dummy-`rustok-agent-mcp` build step in `docker-publish.yml`, and the dropped
  hard-policy example (`skills/rustok-wallet/examples/policy.json`). The MCP is a
  Python package/image now; the spend-limit/budget policy model is intentionally
  not part of the wallet (risk is the user's to accept).
- `cargo`-based checklist in the PR template (replaced with ruff/mypy/pytest).

## [0.2.2] — 2026-05-27

### Changed
- Migrated from `temrjan/rustok` to `rustok-org/mcp`
- Updated all installation URLs to new organization

## [0.2.1] — 2026-05-24

### Added
- Dual-mode transport: HTTP server and stdio for Claude Desktop / Cursor
- GitHub Releases with prebuilt binaries (Linux, macOS Apple Silicon, Windows)
- One-command install script
- Docker image published to GHCR

### Changed
- All supported chains enabled by default (Ethereum, Arbitrum, Base, Optimism, zkSync, Sepolia, Arbitrum Sepolia)
- Removed API key requirement; auth optional via `MCP_API_KEY`

## [0.1.0] — 2026-05-21

### Added
- Initial release of rustok-agent-mcp
- Wallet context, ETH send (preview + execute)
- Aave v3 + ERC-4626 position tracking
- Hard policy gates and audit logging
- Verified on-chain: first agent-executed ETH transfer via Telegram (Sepolia)
