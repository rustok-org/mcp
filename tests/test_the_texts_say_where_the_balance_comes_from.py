"""The texts say where a balance comes from, and who learns of it.

Since 0.11.0 the wallet carries public endpoints and a USDC registry, so a
fresh install reads balances with nothing configured. That convenience moves a
fact from the operator to us: some third party's node now sees the wallet
address and the IP asking about it, and it does so without anyone choosing it.

Three claims must survive every future rewording of these files, because each
is a thing a reader would otherwise assume the other way round:

* a node reading a balance learns the address and the IP;
* what the operator names REPLACES the carried list rather than joining it;
* on Arbitrum two USDC rows are normal, and only the address separates them.

This guard knows nothing about what the wallet does — the core's own tests hold
the behaviour. It holds the description still.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every text a reader meets before or while the wallet reads a chain for them.
HUMAN_TEXTS = (
    REPO_ROOT / "docs" / "CAVEATS.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
    REPO_ROOT / "README.md",
)

# The agent never opens the console, so the sentence the console draws on its
# balance panel cannot reach a reader who only ever sees the agent. This file is
# where it reaches them instead.
AGENT_TEXTS = (REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",)

# Anchors, not prose: matched against whitespace-normalized text, because these
# sentences wrap and a phrase split across two lines is the shape that has
# already hidden from one guard in this suite for five releases.
WATCHER_CLAIM = "learns the address and the IP"
REPLACES_CLAIM = "replaces"
BRIDGED_CLAIM = "USDC.e"


def _read(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_every_text_says_the_node_sees_the_address_and_the_ip() -> None:
    """Carrying endpoints obliges saying who learns of the reading."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in HUMAN_TEXTS + AGENT_TEXTS
        if WATCHER_CLAIM not in _read(path)
    ]
    assert not offenders, (
        "these texts describe the wallet reading a chain but not who learns of it: "
        f"{offenders}. The wallet now reaches a stranger's node without being asked; "
        "a text that leaves that out makes the choice on the reader's behalf."
    )


def test_the_texts_say_a_named_list_replaces_the_carried_one() -> None:
    """The rule a reader would otherwise guess backwards."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in HUMAN_TEXTS
        if REPLACES_CLAIM not in _read(path)
    ]
    assert not offenders, (
        f"these texts do not say what happens to the carried list when one is named: {offenders}. "
        "Guessing 'joined' costs privacy: a request goes to a node the reader did not pick."
    )


def test_the_agent_text_separates_the_two_arbitrum_usdcs() -> None:
    """Two rows with one symbol is the shape an agent silently sums."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in AGENT_TEXTS
        if BRIDGED_CLAIM not in _read(path)
    ]
    assert not offenders, (
        f"the agent text does not name the bridged token: {offenders}. On chain it calls "
        "itself USDC like the native one — an agent told nothing will report one balance."
    )
