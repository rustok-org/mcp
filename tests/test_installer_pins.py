"""Refuse to ship an installer whose pins do not name what it ships.

`scripts/install.sh` carries two identities that decide what a user actually
receives: the digest of the image it pulls, and the hash of the shim it puts on
their PATH. The two are pinned differently, and the difference is the point.

**`WALLET_DIGEST`** cannot be known before the image is published, so it ships
as an all-zero placeholder and the release step fills it in. The placeholder is
fail-closed — an all-zero digest 404s rather than pulling something unverified.
Its shape is checked as well as its non-emptiness: a digest that lost its
`sha256:` prefix would sail past a placeholder-only check and still break every
install.

**`SHIM_SHA256`** is computable from the working tree, so it needs neither a
placeholder nor a shape check — it is simply compared against the shim shipping
beside it, and a placeholder, a malformed value and a stale value all fail that
one comparison. It replaced a commit-SHA pin that could not work: a commit SHA
cannot exist before the commit carrying the shim, so the pin was stale for one
commit of every release, and its guard skipped in CI (depth-1 clone) while
failing locally. See `meta/docs/RELEASE-IDENTITY-MAP.md` §2.5.

Together they are the last gate before the tag is cut, and a tag cut over a bad
pin is dead permanently: by our own policy a published tag is never moved.
"""

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
SHIM = REPO_ROOT / "cli" / "rustok"

PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


def _pin(name: str) -> str:
    match = re.search(rf'^{name}="(.*)"$', INSTALL_SH.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{name} is missing from scripts/install.sh entirely"
    return match.group(1)


def test_the_wallet_digest_is_a_real_pin() -> None:
    """An unfilled or malformed digest installs nothing — or worse, anything."""
    digest = _pin("WALLET_DIGEST")
    assert digest != PLACEHOLDER_DIGEST, (
        "WALLET_DIGEST is still the fail-closed placeholder — the release step "
        "never filled it in. Do not cut a tag from this commit."
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), (
        f"WALLET_DIGEST is not a well-formed digest: {digest!r} "
        "(expected sha256: followed by 64 lowercase hex characters)"
    )


def test_the_pinned_shim_hash_is_the_shim_in_this_tree() -> None:
    """`SHIM_SHA256` must be the hash of the shim shipping beside it.

    This replaces a commit-SHA pin and the two tests that guarded it. The commit
    pin had a defect that could not be fixed in place: a commit SHA cannot exist
    before the commit that carries the shim, so every release passed through a
    state where the pin named the previous release's shim. The guard could not be
    green during the flow it guarded — it skipped in CI (actions/checkout clones
    at depth 1, so the pinned object was unreadable) and failed locally, which is
    to say it never guarded anything at all.

    A content hash is computable from the working tree, so the new shim and its
    correct pin land in the same commit, and this check reads a file rather than
    a git object — it works at depth 1 like any other test.

    One test replaces three: a placeholder, a malformed value and a stale value
    all fail this comparison. There is nothing left for a shape check to add.
    """
    expected = hashlib.sha256(SHIM.read_bytes()).hexdigest()
    pinned = _pin("SHIM_SHA256")
    assert pinned == expected, (
        f"SHIM_SHA256 is {pinned!r} but cli/rustok hashes to {expected!r} — the "
        "installer would refuse the very shim shipping in this release, or worse, "
        "accept a different one. Re-pin it: sha256sum cli/rustok"
    )
