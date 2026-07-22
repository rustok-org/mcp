"""Guard the docs against drifting back off the one-command install path.

Stage 4 / PR-4.1 of the easy-install epic: the wallet installs with ONE command
(`curl … scripts/install.sh | sh`) and is then driven by the `rustok` shim —
`init`, `connect`, `console`. Before this PR the docs knew neither the installer
nor the shim: they taught the manual recipe end to end and INSTALL.md still
promised the shim as "coming". The manual path survives as an explicit appendix
(installing *without* the shim), but it must never again read as the way in.

Three failure modes this locks down — each one has already happened here or was
one edit away:

* **a placeholder shipped** — the installer URL carries an immutable tag, and
  every doc must carry the SAME one. A release that bumps two files out of three
  leaves a silently broken install line behind.
* **a supply-chain overclaim** — `rustok update` pulls by tag and does NOT
  re-run the signature check (the verify-on-update debt is open), so the
  guarantee covers installation, not the lifecycle. The check is *conditional*
  over every doc on purpose: a named list of two files would not fail when a
  third doc starts talking about updating.
* **the shim is documented but unusable** — `install.sh` hard-requires `cosign`
  and edits PATH; "one command" that omits its own preconditions is a lie.

This is a docs grep-invariant: it fails if the docs drift back.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every doc a human reads to install, run or update the wallet.
DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "INSTALL.md",
    REPO_ROOT / "docs" / "TROUBLESHOOTING.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
]

# The ratified install-URL tag (Gate-1, decision Р-2): the tag line that already
# ships this product (wallet-tui-v0.5.0 … v0.7.1). The bare `v0.1.x` namespace
# belongs to the old rustok-mcp python package — reusing it would put two
# unrelated things in one tag namespace.
INSTALL_TAG = "wallet-tui-v0.8.2"
INSTALL_URL = f"https://raw.githubusercontent.com/rustok-org/mcp/{INSTALL_TAG}/scripts/install.sh"

# Any ref in an installer raw-URL, so a drifted tag is caught wherever it hides.
RAW_INSTALL_RE = re.compile(
    r"raw\.githubusercontent\.com/rustok-org/mcp/([^/\s]+)/scripts/install\.sh"
)

# The hardened fetch install.sh's own header prescribes — a doc that drops these
# teaches an unpinned TLS download.
CURL_FLAGS = "--proto '=https' --tlsv1.2"

# Every command the user needs once the one-liner has run.
SHIM_COMMANDS = (
    "rustok init",
    "rustok connect",
    "rustok console",
    "rustok doctor",
    "rustok update",
    "rustok uninstall",
)

# The honesty pair: mentioning the update path obliges naming its limit — BOTH
# halves of it. The signature half alone would let a doc say "unverified" while
# staying silent about the mutable tag the pull resolves through, which is the
# other half of why the guarantee stops at install time.
UPDATE_MENTION = "rustok update"
UPDATE_CAVEATS = ("pulls by tag", "does not re-run the cosign verification")

# Placeholders that must never reach a doc a user copies from.
VERSION_PLACEHOLDERS = ["vX.Y.Z", "<version>", "v0.0.0"]

# The promise INSTALL.md carried until this PR delivered the shim.
STALE_PROMISE = "is coming"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_install_and_readme_teach_the_one_command_install() -> None:
    """The entry points must show the real, hardened, tag-pinned one-liner."""
    for name in ("README.md", "docs/INSTALL.md"):
        text = _read(REPO_ROOT / name)
        assert INSTALL_URL in text, f"{name} must carry the ratified installer URL"
        assert CURL_FLAGS in text, f"{name} must fetch it with {CURL_FLAGS}"


def test_install_documents_the_whole_shim_lifecycle() -> None:
    """Every command a user needs after the install one-liner is documented."""
    text = _read(REPO_ROOT / "docs" / "INSTALL.md")
    missing = [command for command in SHIM_COMMANDS if command not in text]
    assert not missing, f"INSTALL.md does not document: {', '.join(missing)}"


def test_install_documents_the_installer_preconditions() -> None:
    """`cosign` is a hard requirement of install.sh, and PATH editing is opt-out."""
    text = _read(REPO_ROOT / "docs" / "INSTALL.md")
    assert "cosign" in text, "INSTALL.md must name cosign — install.sh dies without it"
    assert "RUSTOK_NO_MODIFY_PATH" in text, "INSTALL.md must document the PATH opt-out"


def test_install_teaches_inspect_before_run() -> None:
    """Piping a script into a shell is only acceptable if reading it first is taught."""
    text = _read(REPO_ROOT / "docs" / "INSTALL.md")
    assert "-o install.sh" in text, "INSTALL.md must show fetching the installer to a file"
    assert "inspect" in text.lower(), "INSTALL.md must tell the reader to inspect it first"


def test_the_skill_sends_the_user_through_the_shim() -> None:
    """The agent-facing skill must hand the user shim commands, not a manual recipe."""
    text = _read(REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md")
    assert "rustok init" in text, "SKILL.md must onboard through `rustok init`"
    assert "rustok connect claude" in text, "SKILL.md must register through `rustok connect`"


def test_no_doc_ships_a_version_placeholder() -> None:
    """A placeholder in a copy-pasteable command is a broken install."""
    offenders: list[str] = []
    for path in DOC_PATHS:
        text = _read(path)
        offenders += [
            f"{path.relative_to(REPO_ROOT)}: {placeholder!r}"
            for placeholder in VERSION_PLACEHOLDERS
            if placeholder in text
        ]
    assert not offenders, "docs ship an unfilled version placeholder:\n  " + "\n  ".join(offenders)


def test_the_shim_is_no_longer_promised_as_coming() -> None:
    """The shim exists now; a doc still promising it is stale by definition."""
    offenders = [
        str(path.relative_to(REPO_ROOT)) for path in DOC_PATHS if STALE_PROMISE in _read(path)
    ]
    assert not offenders, "docs still promise a shipped feature as future work: " + ", ".join(
        offenders
    )


def test_every_installer_url_carries_the_same_ratified_tag() -> None:
    """A release bump that misses one file leaves a broken install line behind."""
    found: list[str] = []
    offenders: list[str] = []
    for path in DOC_PATHS:
        for ref in RAW_INSTALL_RE.findall(_read(path)):
            found.append(ref)
            if ref != INSTALL_TAG:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {ref!r}")
    assert not offenders, (
        f"installer URLs disagree with the ratified tag {INSTALL_TAG!r}:\n  "
        + "\n  ".join(offenders)
    )
    # Without this the check above is vacuously green when the URL is missing.
    assert found, "no doc carries an installer URL at all"


def test_every_doc_that_mentions_updating_admits_the_unverified_pull() -> None:
    """Conditional on purpose: it must also bite in a doc nobody listed here yet."""
    offenders: list[str] = []
    for path in DOC_PATHS:
        text = _read(path)
        if UPDATE_MENTION not in text:
            continue
        missing = [caveat for caveat in UPDATE_CAVEATS if caveat not in text]
        if missing:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: missing {missing}")
    assert not offenders, (
        "these docs document updating without admitting BOTH limits of it "
        f"{list(UPDATE_CAVEATS)}:\n  " + "\n  ".join(offenders)
    )


def test_the_update_caveat_is_actually_exercised() -> None:
    """Positive control: the conditional above must have something to fire on."""
    for name in ("docs/INSTALL.md", "docs/TROUBLESHOOTING.md"):
        assert UPDATE_MENTION in _read(REPO_ROOT / name), (
            f"{name} must document updating (otherwise the honesty check is vacuous)"
        )
