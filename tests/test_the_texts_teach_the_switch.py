"""The texts teach the mode switch honestly — including what it does NOT do.

Proto 4 gives the console a real switch: `read_only` / `supervised` /
`autonomous`, PIN-gated, downgrades included. Two of its edges are exactly the
kind a text quietly loses in a future edit, because both are counter-intuitive
and neither is an error:

* turning autonomy on does not release what was already parked;
* an agent session reads the mode once, at connect — a mid-session switch
  changes enforcement immediately and the agent's tool list only at the next
  connect.

This guard holds the two sentences in place, the same way the one-PIN and
signing guards hold theirs: it knows nothing about what the wallet does — the
core's own tests hold the behaviour — it holds the description still.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every text an agent reads about switching the wallet's mode.
TEXTS = (
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
    REPO_ROOT / "docs" / "CAVEATS.md",
)

# Anchors, not prose: one stable fragment per claim, so a rewording keeps the
# guard honest while a deletion trips it. Matched against whitespace-normalized
# text — prose wraps, and a phrase broken across two lines is the shape that
# has already hidden from one guard in this suite for five releases.
PARKED_CLAIM = "stays parked"
LAG_CLAIM = "reads the wallet's mode once"


def _read(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_every_switch_text_says_parked_items_stay_parked() -> None:
    """Naming the switch obliges saying it releases nothing already parked."""
    offenders = [
        str(path.relative_to(REPO_ROOT)) for path in TEXTS if PARKED_CLAIM not in _read(path)
    ]
    assert not offenders, (
        "these texts teach the mode switch without saying it releases nothing "
        f"already parked: {', '.join(offenders)}. A human who just enabled "
        "autonomy WILL ask why the pending payment did not go out."
    )


def test_every_switch_text_says_the_session_reads_the_mode_at_connect() -> None:
    """The tool-list lag is a fact of the session, and the texts must carry it."""
    offenders = [str(path.relative_to(REPO_ROOT)) for path in TEXTS if LAG_CLAIM not in _read(path)]
    assert not offenders, (
        "these texts teach the mode switch without the connect-time caveat: "
        f"{', '.join(offenders)}. An agent that keeps seeing a tool the core "
        "now refuses needs the texts to have explained why."
    )
