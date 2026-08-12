"""The disclaimer must name every limit of every safeguard, and stay reachable.

A disclaimer exists to not overpromise. That is its only job, and it is the one
job it kept failing at while being written: the first draft claimed the console
approval step was the boundary that stops a misled agent, while `sign_message`
returns a signature without ever reaching that window; the second draft said
"sending funds is gated at the console" flat, while autonomous mode sends
without asking once a human has confirmed it. Both were caught in review, one
paragraph apart, in a text whose entire purpose is to be honest about limits.

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
NAMED_LIMITS = (
    "spending limits",  # there are none: no budget, no per-transaction cap
    "txguard",  # flags risky transactions, does not block them
    "Autonomous mode",  # once confirmed, sends without asking again
    "sign_message",  # returns a signature without the console approval window
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
    missing = [limit for limit in NAMED_LIMITS if limit not in text]
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
