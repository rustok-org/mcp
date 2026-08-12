"""Guard the numbers and the time-relative prose in the published skill.

SKILL.md told every reader the installer was "~150 lines of POSIX sh" while the
script had grown to 321 — and it said so for five releases, in the same breath
that asks the user to read the script before running it. Nobody noticed, because
a number in prose has nothing keeping it honest.

The same class of rot ate the sentence next to it: "Until this release it was
checked in the MCP layer only" shipped unchanged in v0.9.0 through v0.9.4, so
five releases in a row told their reader that something had *just* changed which
had changed long before.

Both are the same defect — a fact frozen at the moment of writing and carried
forward as if still true. Writing the correct number back would only reset the
clock on it, so these tests watch the mechanism instead of the value: one
compares the claim against the file it describes, the other forbids prose that
can only be true in the release that wrote it.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"
INSTALLER = REPO_ROOT / "scripts" / "install.sh"

# "less install.sh      # ~321 lines of POSIX sh"
_LINE_CLAIM = re.compile(r"~(\d+) lines of POSIX sh")

# Prose whose truth expires with the release that shipped it. "this release"
# reads as "the one you are holding", which is false for every later reader.
_TIME_RELATIVE = re.compile(
    r"\b(until this release|in this release|as of this release|this version|this edition)\b",
    re.IGNORECASE,
)


def test_the_installer_line_count_claim_matches_the_installer() -> None:
    """The number in the text is checked against the file it is about."""
    claim = _LINE_CLAIM.search(SKILL.read_text())
    assert claim, (
        "SKILL.md no longer states the installer's size. It asks the user to read "
        "the script before running it; the size is how they judge that cost."
    )
    claimed = int(claim.group(1))
    actual = len(INSTALLER.read_text().splitlines())

    # Rounded prose against an exact file: allow the rounding, not the drift.
    assert abs(claimed - actual) <= 10, (
        f"SKILL.md claims ~{claimed} lines, install.sh has {actual}. "
        "Update the claim — the number is the reader's estimate of what it costs "
        "to check the script they are about to run as their wallet installer."
    )


def test_the_skill_makes_no_claim_that_expires_with_its_release() -> None:
    """No sentence may say 'this release' — every later reader is a later release."""
    offenders = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(SKILL.read_text().splitlines(), start=1)
        if _TIME_RELATIVE.search(line)
    ]
    assert not offenders, (
        "Time-relative prose in the published skill:\n  "
        + "\n  ".join(offenders)
        + "\nName the version instead ('in releases before 0.9.0'): a phrase that "
        "means 'just now' becomes a lie the moment it is republished unchanged."
    )
