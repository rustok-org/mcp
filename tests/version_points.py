"""Every place that carries the wallet version as a single value, declared once.

The version is not written once — it is written in several places that must
agree, and until this module existed the list lived in one test's local
dictionary while the *count* lived in prose beside it. The two could not be kept
honest against each other: 0.11.0 found four homes the hard way, the release
notes for it were assembled from memory, and the sentence that said "six" went
on saying it.

So the list is declared here and nowhere else, and anything that wants to state
how many there are counts them instead of remembering.

`pyproject.toml` is deliberately absent from `VERSION_POINTS`: it is not a point
that must agree with something, it is the thing the others answer to.

Two files carrying the same version in two places (`server.json`) are two
entries, not one — a bump has to touch both, and a reader planning the release
counts edits, not files.

What is deliberately NOT here, so the count does not quietly claim to be the
whole job: the version also appears throughout published prose a reader copies
from — install URLs and `podman run` examples in `README.md`, `docs/INSTALL.md`,
`docs/TROUBLESHOOTING.md`, `docs/CONFIGURATION.md` and the body of `SKILL.md`.
Those are not single addressable values, they are many occurrences of two
patterns, and they are scanned wholesale by
`test_every_image_tag_a_reader_can_copy_matches_the_manifest` and
`tests/test_docs_one_command.py`. A bump edits those too. This registry counts
the points that carry the version *as a value*; the docs are held, but they are
held by a scan, not by an entry here.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def manifest_version() -> str:
    """The one source of truth every point below answers to.

    Parsed as TOML rather than matched as text: a `version = "..."` line inside
    any other table would satisfy a regex and mean something else entirely.
    """
    return str(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])


def _by_pattern(pattern: str) -> Callable[[str], str]:
    """Read a version out of a text file by a regex with exactly one group.

    The group captures the bare `X.Y.Z`, never the `v` prefix or the image
    repository around it, so every point in the registry answers in the same
    shape and a comparison never has to strip anything.
    """
    compiled = re.compile(pattern, re.MULTILINE)

    def read(text: str) -> str:
        match = compiled.search(text)
        assert match, f"no version found for pattern {pattern!r}"
        return match.group(1)

    return read


def _by_json_key(*keys: str | int) -> Callable[[str], str]:
    """Read a version out of a JSON file by key path — parsed, not matched."""

    def read(text: str) -> str:
        value: object = json.loads(text)
        for key in keys:
            assert isinstance(value, dict | list), f"{keys}: {key!r} has nothing to index into"
            value = value[key]  # type: ignore[index]  # narrowed by the assert above
        assert isinstance(value, str), f"{keys}: expected a string, got {type(value).__name__}"
        return value

    return read


def _tag_in_json(*keys: str | int) -> Callable[[str], str]:
    """A JSON value that is an image reference, reduced to its bare version."""
    read_value = _by_json_key(*keys)

    def read(text: str) -> str:
        value = read_value(text)
        match = re.search(r":v([0-9]+\.[0-9]+\.[0-9]+)$", value)
        assert match, f"{keys}: {value!r} does not end in a :vX.Y.Z tag"
        return match.group(1)

    return read


@dataclass(frozen=True)
class VersionPoint:
    """One place a human has to edit when the version changes."""

    label: str
    path: Path
    read: Callable[[str], str]

    def current(self) -> str:
        return self.read(self.path.read_text(encoding="utf-8"))


VERSION_POINTS: tuple[VersionPoint, ...] = (
    VersionPoint(
        "skills/rustok-wallet-tui/SKILL.md (frontmatter)",
        REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md",
        _by_pattern(r"^version: (.+)$"),
    ),
    VersionPoint(
        "skills/rustok-wallet-tui/claw.json",
        REPO_ROOT / "skills" / "rustok-wallet-tui" / "claw.json",
        _by_json_key("version"),
    ),
    VersionPoint(
        "scripts/install.sh (WALLET_VERSION)",
        REPO_ROOT / "scripts" / "install.sh",
        _by_pattern(r'^WALLET_VERSION="(.+)"$'),
    ),
    VersionPoint(
        "cli/rustok (DEFAULT_IMAGE tag)",
        REPO_ROOT / "cli" / "rustok",
        _by_pattern(r'^DEFAULT_IMAGE="ghcr\.io/rustok-org/rustok-wallet-tui:v(.+)"$'),
    ),
    # Added in 0.9.3: the number the built image states about itself, which the
    # console reads and shows to a human. A drift here is the quietest of them —
    # nothing refuses to build, nothing strands a user, the panel simply says the
    # wrong thing to the one person who opened it to find out what they run.
    VersionPoint(
        "Dockerfile.wallet (ARG WALLET_VERSION)",
        REPO_ROOT / "Dockerfile.wallet",
        _by_pattern(r"^ARG WALLET_VERSION=(.+)$"),
    ),
    # Both halves of the MCP registry listing. 0.11.0 found them the hard way:
    # a listing that announces one version next to an image tag naming another
    # misdirects every install that arrives through the registry.
    VersionPoint(
        "server.json (version)",
        REPO_ROOT / "server.json",
        _by_json_key("version"),
    ),
    VersionPoint(
        "server.json (image identifier)",
        REPO_ROOT / "server.json",
        _tag_in_json("packages", 0, "identifier"),
    ),
    # The Smithery listing. It was part of the bump once — CHANGELOG 0.5.0 lists
    # it by name — and then fell out of every list: it sat on v0.9.2 through
    # eight releases while the storefront told people to run that image. Nothing
    # looked at it, which is the entire subject of this file.
    VersionPoint(
        "smithery.yaml (image)",
        REPO_ROOT / "smithery.yaml",
        _by_pattern(r"ghcr\.io/rustok-org/rustok-wallet-tui:v([0-9]+\.[0-9]+\.[0-9]+)"),
    ),
)

# What a reader plans a release against: the manifest plus every point that has
# to follow it. Counted, never written down — the sentence that said "six" was
# true for two releases and then quietly was not.
VERSION_HOME_COUNT = len(VERSION_POINTS) + 1
