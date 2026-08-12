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

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"
INSTALLER = REPO_ROOT / "scripts" / "install.sh"
DISCLAIMER = REPO_ROOT / "DISCLAIMER.md"

# Every published text whose prose can go stale. The disclaimer joins the skill
# because a liability text ages exactly like any other — and it is republished
# unchanged by definition, which is the condition the rot needs.
GUARDED_TEXTS = (SKILL, DISCLAIMER)

# Every doc that tells the reader how big install.sh is. Both ask them to read it
# before running it, so both owe them an honest number.
SIZE_CLAIMANTS = (SKILL, REPO_ROOT / "docs" / "INSTALL.md")

# "less install.sh      # ~321 lines of POSIX sh"
_LINE_CLAIM = re.compile(r"~(\d+) lines of POSIX sh")

# Prose whose truth expires with the release that shipped it. "this release"
# reads as "the one you are holding", which is false for every later reader.
_TIME_RELATIVE_PHRASES = (
    "until this release",
    "in this release",
    "as of this release",
    "this version",
    "this edition",
)

# `\s+` between the words rather than a literal space: prose wraps. In v0.9.4 the
# original offender wrapped mid-phrase — line 248 ended on "Until this", line 249
# began with "release" — so a search for the literal string found the two
# unwrapped occurrences and missed the one this guard exists to catch. Matching
# the whitespace instead of collapsing the text keeps the exact line number too.
_TIME_RELATIVE = re.compile(
    r"\b(" + "|".join(r"\s+".join(phrase.split()) for phrase in _TIME_RELATIVE_PHRASES) + r")\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("path", SIZE_CLAIMANTS, ids=lambda p: p.name)
def test_the_installer_line_count_claim_matches_the_installer(path: Path) -> None:
    """The number in the text is checked against the file it is about.

    Parametrised over every doc that states the size, because the first version
    of this guard read SKILL.md alone — and `docs/INSTALL.md`, the page a user
    actually installs from, went on promising "~150 lines" of a 321-line script
    for four more releases. One file guarded is not the class guarded.
    """
    claim = _LINE_CLAIM.search(path.read_text())
    assert claim, (
        f"{path.name} no longer states the installer's size. It asks the user to "
        "read the script before running it; the size is how they judge that cost."
    )
    claimed = int(claim.group(1))
    actual = len(INSTALLER.read_text().splitlines())

    # Rounded prose against an exact file: allow the rounding, not the drift.
    assert abs(claimed - actual) <= 10, (
        f"{path.name} claims ~{claimed} lines, install.sh has {actual}. "
        "Update the claim — the number is the reader's estimate of what it costs "
        "to check the script they are about to run as their wallet installer."
    )


def _offending_phrases(text: str) -> list[str]:
    """Find the phrases anywhere in `text`, wrapped across lines or not.

    The mutation that first "proved" this guard inserted the phrase on a single
    line, so it never exercised the wrapped shape the original had — a mutation
    has to reproduce the SHAPE of what it stands in for, not only its text.
    """
    offenders = []
    for match in _TIME_RELATIVE.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        phrase = " ".join(match.group().split())
        offenders.append(f"line {line_number}: {phrase}")
    return offenders


def test_the_skill_makes_no_claim_that_expires_with_its_release() -> None:
    """No sentence may say 'this release' — every later reader is a later release."""
    offenders = [
        f"{path.name}: {phrase}"
        for path in GUARDED_TEXTS
        for phrase in _offending_phrases(path.read_text())
    ]
    assert not offenders, (
        "Time-relative prose in a published text:\n  "
        + "\n  ".join(offenders)
        + "\nName the version instead ('in releases before 0.9.0'): a phrase that "
        "means 'just now' becomes a lie the moment it is republished unchanged."
    )
