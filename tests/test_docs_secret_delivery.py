"""Guard the docs against plaintext keyring-password delivery.

Stage 1 of the easy-install epic (PR-1.2): every doc teaches the secret delivery —
`podman secret` (type=env / type=mount) or `RUSTOK_KEYRING_PASSWORD_FILE` — never an
inline password value, an env-block value, or the legacy `--env-file` recipe whose
quotes silently become part of the password (the trap that broke a real onboarding).

This is a docs grep-invariant: it fails if a plaintext recipe is reintroduced.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Every doc that shows how to deliver the keyring password.
DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "INSTALL.md",
    REPO_ROOT / "docs" / "TROUBLESHOOTING.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
    REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
]

# Patterns that reintroduce plaintext password delivery.
#
# The last two close a hole this guard carried until PR-4.1: passing the variable
# through from the caller's environment (`-e RUSTOK_KEYRING_PASSWORD`, no value)
# kept the password out of argv but still landed it in the container's
# `inspect` Config.Env — the same leak class as the retired `--env-file`, only
# quieter, and none of the value-shaped patterns above matched it. Both forms
# discriminate against the legitimate recipes: the trailing ` \` excludes the
# `_FILE=` shell lines, and the closing quote after `PASSWORD` excludes both
# `…_PASSWORD_FILE=…` and `target=RUSTOK_KEYRING_PASSWORD` (verified against
# every occurrence in the five docs).
FORBIDDEN = [
    'RUSTOK_KEYRING_PASSWORD="',  # inline value in a shell example
    '"RUSTOK_KEYRING_PASSWORD": "',  # value inside an MCP-config env block
    "RUSTOK_KEYRING_PASSWORD=%s",  # the legacy env-file printf recipe
    '"--env-file"',  # env-file in MCP-config args
    "--env-file ~/",  # env-file in a runnable shell example
    "-e RUSTOK_KEYRING_PASSWORD \\",  # env passthrough in a shell example
    '"RUSTOK_KEYRING_PASSWORD"',  # env passthrough in MCP-config args
]


def test_docs_never_deliver_the_password_in_plaintext() -> None:
    """No doc may show an inline password value or the env-file recipe."""
    offenders: list[str] = []
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern!r}")
    assert not offenders, (
        "docs reintroduced a plaintext password recipe — deliver via podman secret "
        "or RUSTOK_KEYRING_PASSWORD_FILE instead:\n  " + "\n  ".join(offenders)
    )


def test_docs_teach_the_secret_delivery() -> None:
    """Positive control: the docs actually document the secret/_FILE flow, so the
    forbidden-pattern test can't pass merely because the docs went silent."""
    install = (REPO_ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md").read_text(encoding="utf-8")
    configuration = (REPO_ROOT / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")

    for name, text in (("INSTALL.md", install), ("SKILL.md", skill)):
        assert "podman secret create" in text, f"{name} must teach the podman-secret flow"
        assert "RUSTOK_KEYRING_PASSWORD_FILE" in text, f"{name} must teach the _FILE delivery"
    assert "RUSTOK_KEYRING_PASSWORD_FILE" in configuration, (
        "CONFIGURATION.md must document the RUSTOK_KEYRING_PASSWORD_FILE variable"
    )
