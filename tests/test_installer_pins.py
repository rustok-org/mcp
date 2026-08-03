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
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
SHIM = REPO_ROOT / "cli" / "rustok"

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


def test_the_pinned_shim_is_the_shim_in_this_tree() -> None:
    """A well-formed pin can still point at last release's shim.

    Both release identities went stale the same way once: the version was bumped
    and the pins were not, so the installer would have handed a fresh user the
    previous release's bytes while announcing the new version. The digest cannot
    be checked without the registry, but this one can — `SHIM_COMMIT` names a
    commit in this repository, and what it holds is either today's shim or it is
    not.

    Skips rather than fails when the commit is not present locally (a shallow CI
    clone): a check that cannot read the object has learned nothing, and saying
    so is not the same as passing.
    """
    commit = _pin("SHIM_COMMIT")
    # Re-checked here rather than leaned on from the test above: this value is
    # about to become an argument, and a guard that lives in another function is
    # a guard that can be deleted without this one noticing.
    assert re.fullmatch(r"[0-9a-f]{40}", commit), f"refusing to use {commit!r} as a git ref"
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not on PATH here")
    try:
        pinned = subprocess.run(  # noqa: S603  # absolute git, ref matched against ^[0-9a-f]{40}$ above, no shell
            [git, "show", f"{commit}:cli/rustok"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        pytest.skip(f"commit {commit[:12]} is not readable here (shallow clone)")

    assert pinned == SHIM.read_bytes(), (
        f"SHIM_COMMIT ({commit[:12]}) does not hold the shim in this tree — the "
        "installer would fetch a different `cli/rustok` than the one shipping "
        "here. Re-pin it to the commit that carries the current shim."
    )
