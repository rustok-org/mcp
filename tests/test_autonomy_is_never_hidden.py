"""Every text an agent reads about `execute_transaction` must admit autonomous mode.

S1 made the wallet able to send on its own — once a human confirmed that mode at
the console. Several texts kept saying the opposite, and nobody caught it,
because **none of them was in the diff**: they became false without being
touched. A review that reads a diff is structurally blind to that.

So the guard is a POSITIVE requirement, not a blacklist of forbidden phrases: a
blacklist is satisfied by rewording, while "this text must mention the mode"
fails the moment someone describes the gate as unconditional again.

Its reach is honest and narrow: it covers ONE class — what an agent is told about
`execute_transaction`. The root is wider (any claim can be falsified by a change
that never touches it), and the answer to that is a step in the working method —
sweep by CLAIM after changing behaviour — not a test. This file closes the case
that already cost a release; the method has to close the next one.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
HANDLERS = REPO_ROOT / "src" / "rustok_mcp" / "handlers.py"
SKILL_MD = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"

# `autonomous` / `autonomy` both count: the texts differ in register (a tool
# description, a standing instruction, a card table).
AUTONOMY = re.compile(r"autonom", re.IGNORECASE)

# How much text around the claim counts as "near it". The claim and its exception
# belong in one breath, so the window is a paragraph, not a file: a mention of
# autonomy three screens away does not stop a reader from believing the absolute.
WINDOW = 700


def _windows(path: Path, needle: str) -> list[tuple[int, str]]:
    """Every occurrence of `needle`, with the surrounding text and its line."""
    text = path.read_text(encoding="utf-8")
    found = []
    for match in re.finditer(re.escape(needle), text):
        start = max(0, match.start() - WINDOW // 2)
        window = text[start : match.end() + WINDOW // 2]
        found.append((text.count("\n", 0, match.start()) + 1, window))
    return found


def _assert_admits_autonomy(path: Path, needle: str, what: str) -> None:
    windows = _windows(path, needle)
    assert windows, (
        f"{path.name}: {needle!r} is gone — re-point this guard at where the claim "
        "lives now rather than deleting it; the claim did not stop existing."
    )
    offenders = [line for line, window in windows if not AUTONOMY.search(window)]
    assert not offenders, (
        f"{path.name} line(s) {offenders}: {what} describes the console gate without "
        "admitting autonomous mode. An agent told the wallet cannot send by itself "
        "will not warn the human and will not treat a send as final."
    )


def test_the_tool_description_admits_autonomous_mode() -> None:
    """What an agent reads immediately before deciding to call the tool."""
    _assert_admits_autonomy(
        HANDLERS, "Submit a previewed transaction", "the execute_transaction description"
    )


def test_the_server_instructions_admit_autonomous_mode() -> None:
    """The standing instruction the agent carries for the whole session."""
    _assert_admits_autonomy(
        HANDLERS, "execute_transaction does not decide", "the server instruction"
    )


def test_the_skill_card_admits_autonomous_mode_where_it_promises_the_gate() -> None:
    """Both places the card promises the gate: the guarantee row and the tool table."""
    _assert_admits_autonomy(SKILL_MD, "Sending funds on-chain", "the guarantee row")
    _assert_admits_autonomy(SKILL_MD, "previewed transaction `{preview_id}`", "the tool table row")
