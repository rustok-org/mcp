"""Guard every surface against the fixed-container-name papercut.

The agent launches the wallet container itself. A fixed `--name rustok-wallet-tui`
in an MCP-config example collides the moment anything starts a second instance
(a health probe, a `mcp list`) — the exact failure the first real user hit. The
docs must launch by label and open the console by label discovery, never assume a
fixed name (Stage 0 of the easy-install epic; forensic finding 2026-07-16).

This is a grep-invariant: it fails if the papercut is reintroduced.

Scope note (2026-08-06): this inventory used to be docs-only, and the same broken
command sat in `handlers.py` untouched for a month — the widest surface there is,
since it reaches every connected agent through `initialize` and through the
`next_step` of every parked transaction. The guard was green the whole time. The
source and its tests are in the list now.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Two files talk ABOUT the papercut instead of repeating it: this one carries
# the patterns, and the changelog quotes the broken command in the entry that
# records its removal. History is not rewritten to satisfy a grep.
_EXEMPT = {Path(__file__).resolve(), (REPO_ROOT / "CHANGELOG.md").resolve()}

# Every surface that tells a human or an agent how to run the wallet or open its
# console: docs, the published skill, the instructions the server hands to the
# model, and the tests that pin them. Globbed rather than enumerated — a list
# written from memory is exactly how `handlers.py` sat outside this guard for a
# month while the broken command shipped in it.
SURFACE_PATHS = sorted(
    path
    for path in (
        *REPO_ROOT.glob("*.md"),
        *(REPO_ROOT / "docs").rglob("*.md"),
        *(REPO_ROOT / "skills").rglob("*.md"),
        *(REPO_ROOT / "src").rglob("*.py"),
        *(REPO_ROOT / "tests").rglob("*.py"),
    )
    if path.resolve() not in _EXEMPT
)

# Patterns that reintroduce the fixed-name bug.
FORBIDDEN = [
    "--name rustok-wallet-tui",  # shell run form
    '"--name", "rustok-wallet-tui"',  # MCP-config JSON args form
    "exec -it rustok-wallet-tui rustok-console",  # broken fixed-name console
    "exec -it rustok-wallet-tui core-server",  # broken fixed-name set-pin
]


def test_nothing_pins_the_container_by_fixed_name() -> None:
    """No surface may launch or exec the wallet by a fixed `--name`."""
    offenders: list[str] = []
    for path in SURFACE_PATHS:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern!r}")
    assert not offenders, (
        "the fixed-container-name papercut is back — launch/exec by label "
        "instead:\n  " + "\n  ".join(offenders)
    )


def test_the_inventory_is_not_silently_empty() -> None:
    """Positive control for the glob: a pattern that stops matching is a guard
    that passes forever — quieter than the hand-written list it replaced, and
    the same failure mode. A moved directory or a run from another root must
    break this test, not go unnoticed."""
    assert len(SURFACE_PATHS) > 20, f"the inventory collapsed to {len(SURFACE_PATHS)} files"
    names = {path.name for path in SURFACE_PATHS}
    for expected in ("handlers.py", "INSTALL.md", "SKILL.md", "test_handlers.py"):
        assert expected in names, f"{expected} fell out of the inventory"


def test_install_teaches_label_discovery() -> None:
    """Positive control: INSTALL actually documents the label-based fix, so the
    forbidden-pattern test can't pass merely because the docs went silent."""
    install = (REPO_ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    assert "rustok=wallet" in install, "the MCP config must launch by label"
    assert "rustok.agent=" in install, "the per-agent sub-label must be documented"
    assert "--filter label=rustok.agent=" in install, (
        "opening the console must be by label discovery"
    )
