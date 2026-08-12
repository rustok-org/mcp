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

# The claim that was false. `\s+` between the words rather than literal spaces:
# prose wraps, and a phrase broken across two lines is the shape that already
# hid from one of our guards for five releases.
FALSE_CLAIM = re.compile(
    r"\b(returns?\s+a\s+signature\s+without"
    r"|not\s+console-gated"
    r"|not\s+gated\s+by\s+the\s+console"
    r"|signing\s+is\s+not\s+console-gated"
    r"|is\s+not\s+gated\s+at\s+all)\b",
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
