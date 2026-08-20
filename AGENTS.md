# AGENTS.md — Rustok MCP

> Overrides `meta/AGENTS.md` for `mcp/` subtree.
> This repo now hosts the **Python MCP Server** implementation.

---

## Stack

- **Language:** Python 3.12+
- **Framework:** FastAPI 0.115+ with SSE and stdio transports
- **Package manager:** uv
- **Key deps:** `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`
- **Standards:** `~/Workspace/Codex/standards/python.md` + `~/Workspace/Codex/standards/fastapi.md`

---

## Repository Rules

1. **No secrets in source** — API keys, tokens, passwords only via env vars (`RUSTOK_MCP_*`).
2. **Scripts must be POSIX-compliant** — `install.sh` targets Linux, macOS, Windows (Git Bash). Test with `shellcheck`.
3. **Docker security** — Non-root user, read-only root fs where possible, distroless or slim base image.
4. **No `latest` tag** — GHCR tags must be semver only (`v0.2.0`, `v0.2`, `v0`).
5. **Checksum verification** — Every release artifact must have SHA-256 checksum. Install script verifies it.

---

## Architecture

The MCP Server is a thin JSON-RPC adapter between LLM agents (Claude Desktop, Cursor, cloud agents) and the Rustok Gateway.

```
Claude Desktop (stdio)  →  MCP Server (Python)  →  Gateway (Axum)  →  Core (Rust)
Cloud agent (SSE)       →  /mcp/sse
```

- **No wallet logic here** — all crypto, signing, and key material lives in `core/`.
- **No persistent state** — MCP Server is stateless; state lives in Gateway / Core.
- **Capability-based security** — client selects capabilities on connect (`read_wallet`, `preview_tx`, `execute_tx`).

---

## Gates

```bash
# Python
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest

# Shell scripts
shellcheck scripts/*.sh
```

---

## Release Checklist

The order below is not style — it is the only order that assembles. The image
digest does not exist until the publish runs, the publish requires the bumped
version already on `main`, and the git tag must land on the commit that carries
the filled pins, because users fetch `install.sh` **by tag**. A tag cut before
the pins are filled is dead permanently.

**1 — prep (PR):**
- [ ] Version bumped in **all 9 points** — `pyproject.toml`, which the others
      answer to, plus the 8 that `tests/version_points.py` declares, one entry
      each. Which places those are is not listed here and not remembered;
      `test_every_version_point_matches_the_manifest` holds all of them. The number in this line is checked against that list by
      `test_the_count_in_the_prose_is_the_count_in_the_list`, so it cannot go
      stale the way "six" did for two releases while there were ten. Add a point
      to the registry, not an assertion to a test
- [ ] Published prose is bumped too, and it is NOT in that count: install URLs
      and `podman run` examples live in `README.md`, `docs/INSTALL.md`,
      `docs/TROUBLESHOOTING.md`, `docs/CONFIGURATION.md` and the body of
      `SKILL.md` — roughly sixteen lines, held wholesale by
      `test_every_image_tag_a_reader_can_copy_matches_the_manifest` and
      `tests/test_docs_one_command.py` rather than one entry at a time
- [ ] `CHANGELOG.md` describes the release — including anything user-facing that
      landed since the last tag, not only the last PR. **Start from the draft,
      not from memory:** `sh scripts/release-notes-draft.sh` reads the previous
      release tag, works out which `core` and `console` versions this release
      moves through from the pins in `Dockerfile.wallet` then and now, and prints
      every commit in those ranges plus this repo's own. It sorts into
      likely-user-facing and likely-internal and **drops nothing** — your job is
      to turn lines into prose or delete them on purpose, which is a different
      job from remembering them. 0.11.0 was assembled the old way and lost
      core#124 (a queue-number memory that never expired: payments reported as
      sent, none arrived, only a restart cured it)
- [ ] Docs carry no stale image tag (guarded by
      `test_every_image_tag_a_reader_can_copy_matches_the_manifest`)
- [ ] `ARG CORE_IMAGE` / `CONSOLE_IMAGE` name the intended dependency versions.
      The guard only checks their **shape** (`:vX.Y.Z`, never a floating tag) —
      whether `v0.3.1` should have become `v0.3.2` is not decidable inside this
      repo and stays a human step here

**2 — publish (ops, from `main`):**
- [ ] `gh workflow run wallet-publish.yml --ref main -f version=<X.Y.Z>` —
      **`--ref main`**, because `install.sh` pins the cosign identity to
      `@refs/heads/main`; a dispatch from a tag makes `cosign verify` reject the
      honest image for every user
- [ ] Never dispatch an already-published version (the workflow now refuses;
      `allow_existing_tag` is break-glass only — it rebuilds and replaces)
- [ ] `cosign verify` passes — **with cosign 3.x**. Our signatures are stored as
      OCI referrers, so the tag in GHCR reads `sha256-<digest>` with **no `.sig`
      suffix** and cosign 2.x reports `no signatures found` on a perfectly signed
      image. `install.sh` says so in its own error text; this line used to say
      `.sig` and cost a reviewer an hour

**3 — pin (PR):**
- [ ] **A text that describes BEHAVIOUR the release changes ships in THIS PR, not in
      step 1.** The live guard (`tests/e2e/test_signing_is_refused_e2e.py`) holds the
      texts against the image `WALLET_DIGEST` names, and during step 1 that is still
      the PREVIOUS release's image. A text that got ahead of the bytes turns the guard
      red mid-chain, and the honest fix is the order, not the guard
- [ ] `WALLET_DIGEST` = the digest just published
- [ ] `SHIM_SHA256` = `sha256sum cli/rustok` — **and it belongs in step 1, not
      here.** A content hash is computable from the working tree, so the shim and
      its pin land in the same commit; only the image digest has to wait for the
      publish. It was a commit SHA once, which could not exist before the commit
      carrying the shim — that is why the release used to need three commits and
      why its guard could never be green mid-release
- [ ] No fail-closed placeholders left in `scripts/install.sh`

**4 — tag & publish (ops):**
- [ ] Tag `wallet-tui-v<X.Y.Z>` on the step-3 merge commit — **last**, because
      the documented install command fetches `install.sh` through this tag and
      the shim beside it
- [ ] The GitHub Release writes itself from that tag (`release-shelf.yml`): body
      from the `CHANGELOG.md` section, "Latest" computed against the current one.
      **Nothing to do here on an ordinary release — but check it appeared.** It
      is a step that used to live in memory alone, and memory lost 0.9.8 and
      0.10.0 (both tagged, published, signed, and invisible on the releases page
      until 2026-08-17). If the run failed, the usual cause is a missing
      CHANGELOG section: add it and re-push the tag
- [ ] **Break-glass / manual publish:** no tag push means no release — create it
      by hand, body from the same CHANGELOG section
- [ ] **Withdrawing a version** (`0.9.6 — WITHDRAWN, use 0.9.7` is the precedent)
      stays a human edit AFTER the automation: the workflow writes an ordinary
      release and knows nothing about a decision usually taken a day later
- [ ] **The title is the bare version number** (`0.10.0`), not the descriptive
      line earlier releases carry by hand. Deliberate: guessing a headline from
      the CHANGELOG would be an unreliable heuristic, and honest automation beats
      a clever one. Want a descriptive title — `gh release edit` it afterwards
- [ ] Listings refreshed (ClawHub — then re-check its audit page, Smithery,
      MCP registry); GHCR tags semver only, no `latest`. **This step is now
      load-bearing:** the landing page no longer carries an install command of
      its own, it points here, so a stale listing is a stale install for
      everyone who arrives through the front door.

**5 — the landing page (ops):** the site used to carry its own copy of the
install command, which is how it came to sit two versions behind until a third
party noticed. **It no longer names a version at all** — it points at the skill
page instead — so this step is no longer "update it", it is "confirm it did not
grow a version again".
- [ ] The page still names **no** version — this grep must come back **empty**:
      `curl -s https://rustokwallet.com/ | grep 'wallet-tui-v'`
      A match here is a regression, not a task: whoever put a version back
      created the second copy of the truth this arrangement removed.
- [ ] Nothing else to do here on an ordinary release. A change to the site is
      only needed when the *skill page link* moves, which is not a version event.

**5-bis — when the site does change (rare):** a merge is not a deploy, and the
**merge method** decides whether it becomes one. Vercel blocks a build whose
commit author is not the project owner (Hobby plan, no collaborators), and the
merge button chooses that author: a **squash** merge re-authors the commit to
whoever opened the PR and the deploy blocks; a **rebase** merge keeps the
original author, so a commit already authored by the owner deploys on its own.
Measured both ways on the same page in one day: squash → `Deployment was
blocked`, rebase → `Deployment has completed`, with no dashboard visit at all.
- [ ] The commit is authored by the owner, and the PR is merged with **rebase,
      not squash**. Rebase preserves an author it does not fix — a commit
      authored by someone else still blocks, whichever button is used
- [ ] It blocked anyway → the owner re-triggers from their side: **Redeploy** in
      the dashboard, or a commit to `main` authored by them. This is the
      fallback, not the plan
- [ ] **Check the live page**, not the dashboard

## What holds each release point

The checklist above says what to do and in what order. This table answers a
different question — **what happens if you forget** — and the two are not the
same list. Written 2026-08-17, after two releases went missing from the releases
page: the step that lost them was in nobody's list, and nothing noticed for
eleven days.

| Point | Step | Held by |
|---|---|---|
| every point that carries the version as a value — declared in `tests/version_points.py`, not listed here | 1 | `test_every_version_point_matches_the_manifest` + the publish workflow's own gate (it refuses to run on a mismatch) |
| the **count** of those points, wherever prose states it — this file and the test's own docstring | 1 | `test_the_count_in_the_prose_is_the_count_in_the_list` — it said six for two releases while there were ten |
| `pyproject.toml` reading the same to TOML and to the publish gate's `sed` | 1 | `test_both_readings_of_the_manifest_agree` — otherwise the divergence surfaces two steps later as an opaque refusal from `wallet-publish.yml` |
| the image the shim harness expects | 1 | derived from the manifest, not typed: seven byte-exact copies used to live in `tests/shim/run-tests.sh`, and the harness now refuses to run at all if the manifest has no version |
| the version the image states about itself | 1 | `test_the_core_version_the_panel_states_is_the_core_the_image_is_built_from` + a check inside `Dockerfile.wallet` (the build fails) |
| `CHANGELOG.md` section for the release | 1 | **`release-shelf.yml`** — no section, no release, and the run is red |
| image tags in copy-paste sources (`SKILL.md`, `docs/INSTALL.md`, `docs/TROUBLESHOOTING.md`, `docs/CONFIGURATION.md`) | 1 | `test_every_image_tag_a_reader_can_copy_matches_the_manifest` — it matches `ghcr.io/…:vX.Y.Z` and nothing else |
| installer URLs pinned by tag (the same docs plus `README.md` and `DISCLAIMER.md`) | 1 | `tests/test_docs_one_command.py` — a **different** token from the row above, and until 0.12.0 its `INSTALL_TAG` was typed by hand, which let a release that forgot both the docs and the constant stay green |
| `CORE_IMAGE` / `CONSOLE_IMAGE` versions | 1 | **half** — the guard checks the shape (`:vX.Y.Z`), never whether the number is right. That part is human, deliberately |
| dispatch with `--ref main` | 2 | human; a mistake surfaces later, as `cosign verify` rejecting the image for users |
| signature, and that it verifies | 2 | the publish workflow itself (anti-vacuous step) |
| `WALLET_DIGEST`, `SHIM_SHA256`, no placeholders left | 3 | `tests/test_installer_pins.py` |
| tag on the step-3 commit | 4 | human — and a tag cut before the pins are filled is **permanently** dead |
| **GitHub Release** | 4 | **`release-shelf.yml`** (since 2026-08-17; before that: nothing) |
| listings — ClawHub, Smithery, MCP registry | 4 | **nothing.** External services; a tag cannot reach them. Stays human |
| the landing page names no version | 5 | **nothing automatic** — a `curl … \| grep` run by hand |
| the release notes being **complete** | 1 | **nothing, deliberately.** `scripts/release-notes-draft.sh` assembles the draft, but a line deleted from it is gone. Checking completeness means reading the private `core` from this public repository's CI, and that perimeter costs more than the defect |

The points held by nothing at all are the listings, the landing page, and the
completeness of the notes — no number here, because the list is the count and a
number beside it is one more thing to keep true. Two of the three are the last
things anyone does; completeness is the first, and it is the one that already
went wrong. Treat them as the
ones most likely to be skipped, because they are.
