"""Refuse to ship an installer whose immutable pins were never filled in.

`scripts/install.sh` carries two identities that decide what a user actually
receives: the image digest it pulls and the commit it fetches the shim from.
Both ship as all-zero placeholders so that an unfilled release fails loudly
instead of installing something unverified — the all-zero refs 404 and carry no
signature.

That fail-closed default is the safety net, not the goal. The release step must
replace both, and this test is what makes forgetting impossible: it is the last
gate before the tag is cut, and a tag pointing at placeholder pins is dead
permanently — by our own policy a published tag is never moved.

Shape is checked too, not just "not zero": a digest that lost its `sha256:`
prefix or a commit truncated to a short SHA would both sail past a
placeholder-only check and still break every install.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"

PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
PLACEHOLDER_COMMIT = "0" * 40


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


def test_the_shim_commit_is_a_real_pin() -> None:
    """A short or unfilled SHA makes the shim fetch a 404, or a moving target."""
    commit = _pin("SHIM_COMMIT")
    assert commit != PLACEHOLDER_COMMIT, (
        "SHIM_COMMIT is still the fail-closed placeholder — the release step "
        "never filled it in. Do not cut a tag from this commit."
    )
    assert re.fullmatch(r"[0-9a-f]{40}", commit), (
        f"SHIM_COMMIT is not a full 40-character commit SHA: {commit!r} — an "
        "abbreviated SHA is not an immutable identity"
    )
