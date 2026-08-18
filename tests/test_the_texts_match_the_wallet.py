"""Part B of the two-part guard: the texts carry the true description of signing.

Every published text said `sign_message` returns a signature without the console
approval window. The wallet refuses it outright, in every mode, and has since
core v0.4.0 — `(_, SignMessage | SignTypedData) => Decision::Deny`. Nine places
said it, a spec, a self-check and three review rounds passed over it, and the
call that refutes it took seven seconds.

This half guards PRESENCE: the texts must carry the true formulation, and must
not carry the false one. It cannot know which of those is true — a text has no
feature that separates a correct description of behaviour from a wrong one.
That is what `tests/e2e/test_signing_is_refused_e2e.py` is for: it asks the
shipped image. Neither half is worth much alone. The live half does not read
the texts, so restoring the old sentence would not trouble it; this half does
not know what the wallet does, so it would happily guard a lie. Together the
sentence can neither drift nor go missing.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every text a human or an agent reads about what this wallet will sign.
TEXTS = (
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "claw.json",
    REPO_ROOT / "DISCLAIMER.md",
    REPO_ROOT / "docs" / "CAVEATS.md",
)

# The claim that was false, in every wording it has actually worn. `\s+` between
# the words rather than literal spaces: prose wraps, and a phrase broken across
# two lines is the shape that already hid from one of our guards for five
# releases.
#
# The last alternative is here because the first version of this list was built
# from the wordings I could remember, and a tenth place — a "what changed" entry
# saying the tool "never reaches the console approval window" — sailed straight
# through a green suite. A list of known phrasings is a lower bound on the claim,
# never the claim itself; it earns its keep only paired with the live half, which
# does not care how a sentence is worded.
FALSE_CLAIM = re.compile(
    r"\b(returns?\s+a\s+signature\s+without"
    r"|not\s+console-gated"
    r"|not\s+gated\s+by\s+the\s+console"
    r"|signing\s+is\s+not\s+console-gated"
    r"|is\s+not\s+gated\s+at\s+all"
    r"|never\s+reach(?:es|ing)?\s+the\s+(?:console\s+)?approval\s+window)\b",
    re.IGNORECASE,
)

# The true one, in the form every text must be able to show. "refus" covers
# refuse/refused/refuses without pinning the tense a sentence happens to need.
TRUE_CLAIM = re.compile(r"sign_message[^.]{0,120}?refus", re.IGNORECASE | re.DOTALL)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_text_claims_the_wallet_signs_without_the_console() -> None:
    """The false sentence must be gone from every text, in every wording it had."""
    offenders = []
    for path in TEXTS:
        text = _read(path)
        for match in FALSE_CLAIM.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            offenders.append(
                f"{path.relative_to(REPO_ROOT)}:{line_number}: {' '.join(match.group().split())}"
            )
    assert not offenders, (
        "a text still says the wallet signs without console approval:\n  "
        + "\n  ".join(offenders)
        + "\nThe wallet refuses sign_message outright, in every mode. See "
        "tests/e2e/test_signing_is_refused_e2e.py, which asks the image itself."
    )


def test_every_text_that_names_sign_message_says_it_is_refused() -> None:
    """Naming the tool obliges saying what it does — silence reads as "it works"."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in TEXTS
        if "sign_message" in _read(path) and not TRUE_CLAIM.search(_read(path))
    ]
    assert not offenders, (
        "these texts name sign_message without saying it is refused: "
        + ", ".join(offenders)
        + ". A tool listed with no stated limit reads as a tool that works."
    )


# ---------------------------------------------------------------------------
# Part B2: the listing description, where a capability list and a refusal clause
# spell the same word.
#
# The guard above is keyed to the token `sign_message`. The listing does not use
# it: it writes "sign messages", two words. One character of difference — an
# underscore against a space — and the check never looked at the file at all. It
# was not satisfied by a nearby refusal; it never fired.
#
# Reading prose cannot separate "we do this" from "we refuse this" when both
# spell `sign`. That is a job for a language, not for a test, and any heuristic
# has a counterexample. So the check is inverted: every mention of signing in the
# description must lie INSIDE one sanctioned clause, and no other mention may
# exist. Rigid on purpose — the clause is a load-bearing public claim, and moving
# it should cost a deliberate edit here.
#
# Scope is the description field only. DISCLAIMER.md and CAVEATS.md discuss
# signing in prose at length and legitimately so; the presence/absence pair above
# is their guard. This one guards the string that a marketplace truncates.
#
# What this cannot do: it does not know whether the sanctioned clause is TRUE.
# `tests/e2e/test_signing_is_refused_e2e.py` asks the image that question.

SANCTIONED_CLAUSE = "message signing is refused outright, in every mode"

# `\bsign\w*` catches sign, signs, signing, sign_message; the word boundary keeps
# it off "design" and "assign".
SIGN_WORD = re.compile(r"\bsign\w*", re.IGNORECASE)


def _claw_description() -> str:
    return json.loads(_read(REPO_ROOT / "skills" / "rustok-wallet-tui" / "claw.json"))[
        "description"
    ]


def _skill_description() -> str:
    for line in _read(REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md").splitlines():
        if line.startswith("description:"):
            return line.removeprefix("description:").strip()
    raise AssertionError("SKILL.md front matter has no description field")


DESCRIPTIONS = (("claw.json", _claw_description), ("SKILL.md", _skill_description))


def test_the_listing_description_mentions_signing_only_to_refuse_it() -> None:
    """A capability list that names signing is a promise, whatever follows it."""
    offenders = []
    for name, load in DESCRIPTIONS:
        outside = load().replace(SANCTIONED_CLAUSE, "")
        for match in SIGN_WORD.finditer(outside):
            offenders.append(f"{name}: {match.group()}")
    assert not offenders, (
        "the listing description mentions signing outside the refusal clause: "
        + ", ".join(offenders)
        + f". The only sanctioned mention is {SANCTIONED_CLAUSE!r}. The wallet "
        "refuses sign_message in every mode; naming it anywhere else is a promise."
    )


def test_the_listing_description_still_carries_the_refusal() -> None:
    """Without this, deleting the clause would make the check above pass empty."""
    missing = [name for name, load in DESCRIPTIONS if SANCTIONED_CLAUSE not in load()]
    assert not missing, (
        "the refusal clause is gone from: "
        + ", ".join(missing)
        + f". Expected verbatim: {SANCTIONED_CLAUSE!r}"
    )
