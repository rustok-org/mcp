"""The texts describe ONE secret the person holds — a PIN they chose — and one
backup, the twelve words.

For four releases the wallet asked for two: a keyring password the person typed
at `rustok init`, and a six-digit PIN the core minted and printed beside the
recovery phrase. The console then asked for the second, and people brought the
first — reported live, 2026-08-08, and patched with a sentence in the banner
saying "this PIN is NOT the keyring password". The one-PIN change removes the
cause: `init` asks the person to CHOOSE the PIN, generates the password itself,
and prints only the phrase.

Ten texts described the old flow. Every one of them had to move, and the
sentence "prints the 12 words + PIN" is short, natural, and exactly what a
future edit would type back in from memory. This guard holds the texts to the
new description: no text may say the PIN is printed, minted, issued or backed
up alongside the phrase; and every text that teaches `rustok init` says the
person chooses the PIN.

Like the signing guard beside it, this half knows nothing about what the wallet
does — it holds the description still. The binary's own tests (core-server's
`one_shot_commands`) hold the behaviour. Neither is worth much alone.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every text a human or an agent reads about what `rustok init` produces.
TEXTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "INSTALL.md",
    REPO_ROOT / "docs" / "TROUBLESHOOTING.md",
    REPO_ROOT / "docs" / "CAVEATS.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
    REPO_ROOT / "scripts" / "install.sh",
)

# The old flow, in every wording it has actually worn across these files. `\s+`
# between words, not literal spaces: prose wraps, and a phrase broken across two
# lines is the shape that hid from a guard for five releases; `\**` around
# words because markdown emphasis (`**PIN**`) sits between them in the docs. The optional
# groups exist because the sentence was written with and without each of those
# words in different files.
OLD_FLOW = re.compile(
    r"\b(?:"
    # "prints the 12 words + PIN", "12-word phrase and the approval PIN"
    r"12(?:-|\s+)words?\**\s+(?:recovery\s+)?(?:phrase\s+)?(?:\+|and)\s+(?:the\s+)?\**(?:6-digit\s+)?(?:approval\s+)?PIN"
    # "prints … the approval PIN exactly once / ONCE"
    r"|prints?\s+[^.\n]{0,80}?PIN\s+(?:exactly\s+)?once"
    r"|PIN\s+(?:is\s+)?printed\s+(?:only\s+)?(?:once|when)"
    # "back up the 12 words and the PIN", "back both up", "write both down"
    r"|back\s+up\s+[^.\n]{0,60}?\band\s+the\s+\**PIN\b"
    r"|write\s+both\s+down"
    # "asks for a keyring password" — the person no longer types one at init
    r"|asks\s+for\s+a\s+keyring\s+password"
    r"|keyring\s+password\s+twice"
    # "the wallet volume + password" offered as a backup
    r"|volume\s+\+\s+password"
    r")",
    re.IGNORECASE,
)

# The one-PIN description every text that teaches `rustok init` must carry:
# the person CHOOSES the PIN. Any of these forms.
NEW_FLOW = re.compile(
    r"\b(?:you\s+)?choos(?:e|es|ing)\s+(?:a\s+|the\s+|one\s+)?(?:6-digit\s+)?(?:approval\s+)?PIN"
    r"|PIN\s+(?:you|they)\s+ch(?:o|oo)se",
    re.IGNORECASE,
)

# The texts that actually TEACH `rustok init` (the others only mention the PIN
# in passing — the console asks for it, do not paste it in chat — and need not
# restate how it was chosen).
TEACHES_INIT = re.compile(r"rustok\s+init\b")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_text_describes_the_two_secret_flow() -> None:
    hits: list[str] = []
    for path in TEXTS:
        text = _read(path)
        for m in OLD_FLOW.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.relative_to(REPO_ROOT)}:{line}: {m.group(0)!r}")
    assert not hits, (
        "these texts still describe the old two-secret flow (a printed/minted PIN, "
        "a typed keyring password, the volume as a backup). The person chooses ONE "
        "PIN at `rustok init` and the phrase is the only backup:\n  " + "\n  ".join(hits)
    )


def test_every_text_that_teaches_init_says_the_person_chooses_the_pin() -> None:
    missing: list[str] = []
    for path in TEXTS:
        text = _read(path)
        if TEACHES_INIT.search(text) and not NEW_FLOW.search(text):
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert not missing, (
        "these texts teach `rustok init` but never say the person CHOOSES the PIN — "
        "a reader would not learn there is only one code, and that it is theirs:\n  "
        + "\n  ".join(missing)
    )


def test_the_guard_recognises_the_sentences_that_were_actually_there() -> None:
    # The wordings this guard exists for, lifted from the files as they were on
    # main before the one-PIN change. If a future edit narrows OLD_FLOW until it
    # no longer matches these, the guard has stopped guarding.
    was_there = (
        "creates the wallet — prints the 12 words + PIN once",
        "prints the 12-word phrase and the approval PIN ONCE",
        "It prints the 12-word recovery phrase and the approval PIN exactly once",
        "Back up the **12 words** and the **PIN** offline",
        "Write both down offline",
        "`rustok init` asks for a keyring password and stores it",
        "It asks for a keyring password twice",
        "or the wallet volume + password",
        "The PIN is printed only when the wallet is created",
        "prints the 12-word\nrecovery phrase + approval PIN",  # wrapped, entrypoint.sh:8-9
    )
    for sentence in was_there:
        assert OLD_FLOW.search(sentence), f"guard no longer catches: {sentence!r}"
