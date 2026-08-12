"""The disclaimer must name every limit of every safeguard, and stay reachable.

A disclaimer exists to not overpromise. That is its only job, and it is the one
job it kept failing at while being written: one draft said "sending funds is
gated at the console" flat, while autonomous mode sends without asking once a
human has confirmed it; another described `sign_message` as an ungated hole,
which review then sharpened — and which live acceptance of the release then
refuted outright, because the wallet refuses to sign at all. Three wrong
sentences about limits, in the one text whose entire purpose is to state them
correctly, and every one of them was written by someone reading our own earlier
documents instead of asking the wallet.

So the guards below are POSITIVE requirements, in the shape
`test_autonomy_is_never_hidden.py` established: a blacklist of forbidden claims
is satisfied by rewording, while "this text must name that limit" fails the
moment the limit stops being named.

`sign_message` gets its own test on top of the list test. It is not padding: the
capability ceiling was once enforced in the Python layer only, and a published
image with a `read_wallet` ceiling returned a real 65-byte signature over the
gateway's own route. That is the one place where our advertised protection has
actually been pierced, so the text that describes it earns a guard of its own.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DISCLAIMER = REPO_ROOT / "DISCLAIMER.md"
SKILL = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"
README = REPO_ROOT / "README.md"

# The canonical home of the full text. Both entry points link here rather than
# repeating it: two copies of a liability text drift, and the copy that drifts
# is the one nobody rereads.
DISCLAIMER_URL = "https://github.com/rustok-org/mcp/blob/main/DISCLAIMER.md"

# Every safeguard whose limit the wallet has, named the way the reader meets it.
# Dropping one turns "here is every limit" into a lie of omission — which is the
# failure mode a disclaimer is written to avoid in the first place.
#
# Split by what the token IS. `sign_message` and `txguard` are identifiers that
# exist in the code, and a reader has to be able to grep for exactly them. The
# other two are prose: a limit named with a lowercase letter is still named, and
# a guard that fails on a legitimate rewording teaches its author to ignore it.
NAMED_IDENTIFIERS = (
    "sign_message",  # refused outright in every mode; parking is planned, not built
    "txguard",  # flags risky transactions, does not block them
)
NAMED_IN_PROSE = (
    "spending limits",  # there are none: no budget, no per-transaction cap
    "autonomous mode",  # once confirmed, sends without asking again
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_disclaimer_names_the_signing_bypass() -> None:
    """`sign_message` skips the console: the one gap that was once real."""
    assert DISCLAIMER.exists(), "DISCLAIMER.md is the canonical text and must exist"
    assert "sign_message" in _read(DISCLAIMER), (
        "DISCLAIMER.md must name sign_message as ungated. The console boundary "
        "covers sending funds and not signing, and a published image has already "
        "returned a real signature past a capability ceiling once."
    )


def test_the_disclaimer_names_every_limit() -> None:
    """The honesty list may grow. It may not quietly shrink."""
    assert DISCLAIMER.exists(), "DISCLAIMER.md is the canonical text and must exist"
    text = _read(DISCLAIMER)
    missing = [name for name in NAMED_IDENTIFIERS if name not in text]
    missing += [name for name in NAMED_IN_PROSE if name not in text.lower()]
    assert not missing, (
        "DISCLAIMER.md stopped naming: "
        + ", ".join(missing)
        + ". A safeguard whose limit goes unnamed reads as a safeguard without one."
    )


def test_both_entry_points_reach_the_disclaimer() -> None:
    """The skill page and the repo README each carry the link, or it is unread."""
    for path in (SKILL, README):
        assert DISCLAIMER_URL in _read(path), (
            f"{path.relative_to(REPO_ROOT)} must link to {DISCLAIMER_URL}. "
            "The link is absolute on purpose: SKILL.md is rendered on the ClawHub "
            "page, where a repository-relative path does not resolve."
        )
