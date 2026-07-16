"""Guard the docs against the fixed-container-name papercut.

The agent launches the wallet container itself. A fixed `--name rustok-wallet-tui`
in an MCP-config example collides the moment anything starts a second instance
(a health probe, a `mcp list`) — the exact failure the first real user hit. The
docs must launch by label and open the console by label discovery, never assume a
fixed name (Stage 0 of the easy-install epic; forensic finding 2026-07-16).

This is a docs grep-invariant: it fails if the papercut is reintroduced.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every doc that shows how to run the wallet or open its console.
DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "INSTALL.md",
    REPO_ROOT / "docs" / "TROUBLESHOOTING.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
]

# Patterns that reintroduce the fixed-name bug.
FORBIDDEN = [
    "--name rustok-wallet-tui",  # shell run form
    '"--name", "rustok-wallet-tui"',  # MCP-config JSON args form
    "exec -it rustok-wallet-tui rustok-console",  # broken fixed-name console
    "exec -it rustok-wallet-tui core-server",  # broken fixed-name set-pin
]


def test_docs_never_pin_the_container_by_fixed_name() -> None:
    """No doc may launch or exec the wallet by a fixed `--name`."""
    offenders: list[str] = []
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern!r}")
    assert not offenders, (
        "docs reintroduced the fixed-container-name papercut — launch/exec by "
        "label instead:\n  " + "\n  ".join(offenders)
    )


def test_install_teaches_label_discovery() -> None:
    """Positive control: INSTALL actually documents the label-based fix, so the
    forbidden-pattern test can't pass merely because the docs went silent."""
    install = (REPO_ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    assert "rustok=wallet" in install, "the MCP config must launch by label"
    assert "rustok.agent=" in install, "the per-agent sub-label must be documented"
    assert "--filter label=rustok.agent=" in install, (
        "opening the console must be by label discovery"
    )
