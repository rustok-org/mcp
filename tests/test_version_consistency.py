"""Keep every place that names the wallet version telling the same story.

The list of those places is not here — it is declared once in
`tests/version_points.py`, because it used to live in this file's local
dictionary while the *count* lived in prose beside it, and the two drifted apart
in 0.11.0: the prose said six, the release found ten the hard way, and nothing
noticed until a human did.

One version, 9 homes — a mismatch blocks the release, strands users, or makes
the panel that answers "what am I running" answer wrong:

* `wallet-publish.yml` refuses to publish unless its `version` input equals
  `pyproject.toml` — a stale manifest blocks the release outright;
* the tag in `DEFAULT_IMAGE` is what `rustok update` pulls and what `connect`
  stamps into every agent config, so a shim left behind on an old tag keeps
  users on an old image no matter what they do;
* this repo has already shipped this exact bug once — a 0.3.2 manifest against a
  0.4.x tag line, named in `wallet-publish.yml`'s own header as the reason its
  version gate exists.

Deliberately an INVARIANT, not a "no 0.7.1 anywhere" grep: a one-off ban on the
previous string passes vacuously the moment 0.9.0 lands and would have to be
rewritten every release. These tests are green before and after a bump — their
red proof comes from mutation (desynchronise one point and it names that point).

The number above is prose, and prose rots. It is held by
`test_the_count_in_the_prose_is_the_count_in_the_list` below, the same way
`test_skill_numbers_do_not_rot` holds the installer's line count: checked
against the list it describes, rather than deleted or frozen.
"""

import re
from pathlib import Path

from tests.version_points import (
    PYPROJECT,
    REPO_ROOT,
    VERSION_HOME_COUNT,
    VERSION_POINTS,
    manifest_version,
)

SKILL_MD = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"
DOCKERFILE = REPO_ROOT / "Dockerfile.wallet"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def _first_match(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name}: no version found for pattern {pattern!r}"
    return match.group(1)


def manifest_version_as_the_publish_gate_reads_it() -> str:
    r"""The version as `wallet-publish.yml:68` computes it — by line, not by TOML.

    Not a second way to read the file: the workflow's own gate runs
    `sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1`, and a
    release only assembles if that string equals the one everything else uses.
    This function exists so a divergence is named HERE, by a red test, instead of
    surfacing two steps later as an opaque refusal from the publish workflow.

    Its only consumer is `test_both_readings_of_the_manifest_agree`.
    """
    return _first_match(PYPROJECT, r'^version = "(.*)"$')


# The exact line the mirror above stands for. Compared as text against the
# workflow, so a change there turns this red instead of silently retiring it.
PUBLISH_GATE_SED = (
    "MANIFEST_VERSION=$(sed -n 's/^version = \"\\(.*\\)\"$/\\1/p' pyproject.toml | head -n 1)"
)


def test_every_version_point_matches_the_manifest() -> None:
    """Every point in the registry answers what `pyproject.toml` says.

    A mismatch blocks the release, strands users, or makes the panel that answers
    "what am I running" answer wrong. Which places count is not decided here —
    see `tests/version_points.py`, and add a point there rather than an assertion
    here, so the count stays computable.
    """
    expected = manifest_version()
    drifted = [
        f"{point.label}: {found!r} != {expected!r}"
        for point in VERSION_POINTS
        if (found := point.current()) != expected
    ]
    assert not drifted, (
        f"version drift against pyproject.toml ({expected!r}) — the publish workflow's "
        "own gate rejects a mismatched manifest, and a stale image tag strands users "
        "on an old wallet:\n  " + "\n  ".join(drifted)
    )


def test_both_readings_of_the_manifest_agree() -> None:
    """Our parser and the publish gate's parser must see the same string.

    Everything in this repo reads the manifest as TOML. `wallet-publish.yml:68`
    reads it with `sed`, by line, and refuses to publish when its input does not
    equal what that sed prints. The two agree today by construction — a
    `version = "..."` line added to any table ABOVE `[project]` would part them,
    and the release would then fail inside the publish workflow, two steps after
    the mistake, with an error naming neither cause.

    A red here names both strings at the moment the mistake lands.
    """
    # Guard the guard: this test is a mirror, and a mirror of something that
    # moved reflects nothing. If the workflow changes how it reads the manifest,
    # comparing tomllib against a pattern nobody runs any more would stay green
    # while the property it stands for is gone.
    workflow = (REPO_ROOT / ".github" / "workflows" / "wallet-publish.yml").read_text(
        encoding="utf-8"
    )
    assert PUBLISH_GATE_SED in workflow, (
        "wallet-publish.yml no longer reads the manifest the way this test mirrors "
        f"({PUBLISH_GATE_SED!r}). Update the mirror with it — until then this "
        "comparison stands for nothing."
    )

    semantic = manifest_version()
    as_published = manifest_version_as_the_publish_gate_reads_it()
    assert semantic == as_published, (
        f"pyproject.toml reads as {semantic!r} when parsed as TOML but "
        f"{as_published!r} to the publish workflow's own gate "
        "(wallet-publish.yml, `sed -n 's/^version = \"...\"$/.../p' | head -n 1`). "
        "The release would be refused by that gate with no explanation of why."
    )


# "One version, 8 homes" — the module docstring above, and "all 8 points" in the
# release checklist. Both are prose, and prose is what rotted last time.
_PROSE_COUNTS = (
    (Path(__file__), re.compile(r"One version, (\d+) homes")),
    (AGENTS_MD, re.compile(r"Version bumped in \*\*all (\d+) points\*\*")),
)


def test_the_count_in_the_prose_is_the_count_in_the_list() -> None:
    """A number written in a sentence has nothing keeping it honest.

    `test_skill_numbers_do_not_rot` already holds the installer's line count this
    way: the claim is compared against the thing it describes rather than deleted
    or frozen. The count of version points is the same class of fact — it was
    wrong for two releases ("six" while there were ten), and it is what a reader
    plans a release against.
    """
    wrong = []
    for path, pattern in _PROSE_COUNTS:
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        assert match, (
            f"{path.name}: the sentence this guard watches is gone (pattern "
            f"{pattern.pattern!r}). Rewording is fine — update the pattern with it; "
            "a guard that silently stops matching protects nothing."
        )
        if int(match.group(1)) != VERSION_HOME_COUNT:
            wrong.append(
                f"{path.name}: says {match.group(1)}, the registry holds {VERSION_HOME_COUNT}"
            )
    assert not wrong, (
        "the prose and the list disagree about how many places carry the version — "
        "the list in tests/version_points.py is the one that is true:\n  " + "\n  ".join(wrong)
    )


def test_the_core_version_the_panel_states_is_the_core_the_image_is_built_from() -> None:
    """`CORE_VERSION` is a derived value, and this proves it is still derived.

    The identity panel names the core the wallet is running. That number has to
    come from the pin the image is actually built from — `CORE_IMAGE` — and not
    from a second constant that merely happens to agree today. Bump the pin,
    forget the constant, and the panel keeps stating the previous core with
    total confidence.

    The Dockerfile enforces this at build time too, in a shell where suffix
    stripping works. This test is the same invariant one step earlier: a red
    `pytest` instead of a red image build, and it does not need a builder.

    Why not derive it in the Dockerfile and skip the constant entirely: measured,
    not assumed — `ENV X=${CORE_IMAGE##*:}` under buildah yields the whole
    reference, so the panel would have stated `ghcr.io/rustok-org/…` as a
    version. An expansion that silently lies is worse than a check that refuses.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    core_image = _first_match(DOCKERFILE, r"^ARG CORE_IMAGE=(.+)$")
    core_version = _first_match(DOCKERFILE, r"^ARG CORE_VERSION=(.+)$")

    assert "@" not in core_image, (
        f"CORE_IMAGE {core_image!r} is pinned by digest and carries no tag, so "
        "CORE_VERSION cannot be checked against it — the build refuses this too"
    )
    tag = core_image.rsplit(":", 1)[-1]
    assert core_version == tag, (
        f"ARG CORE_VERSION is {core_version!r} but the image is built from "
        f"{core_image!r} (tag {tag!r}) — the panel would state a core this "
        "wallet does not contain"
    )

    # Guard the guard: the build-time check is what protects a build that passes
    # --build-arg CORE_VERSION by hand, which this file cannot see. If someone
    # deletes it, this test alone would still pass while the real protection is
    # gone — so assert the check exists.
    assert '[ "${CORE_IMAGE##*:}" = "${CORE_VERSION}" ]' in text, (
        "the build-time equality check is gone from Dockerfile.wallet — a build "
        "given a hand-written --build-arg CORE_VERSION would ship a panel "
        "stating a core it was not built from, and nothing here would notice"
    )


# Every file whose text a reader copies into their own terminal. SKILL.md is the
# ClawHub listing; the docs are what the listing and the README send people to.
COPY_PASTE_SOURCES = (
    SKILL_MD,
    REPO_ROOT / "docs" / "INSTALL.md",
    REPO_ROOT / "docs" / "TROUBLESHOOTING.md",
    REPO_ROOT / "docs" / "CONFIGURATION.md",
)

# The image tag, never a bare version string. `docs/TROUBLESHOOTING.md` says the
# file delivery "arrived in 0.8.3" — history, not a pin, and a check that matched
# bare versions would demand that sentence be rewritten every release until it
# said something false.
IMAGE_TAG_RE = re.compile(r"ghcr\.io/rustok-org/rustok-wallet-tui:v([0-9]+\.[0-9]+\.[0-9]+)")


def test_every_image_tag_a_reader_can_copy_matches_the_manifest() -> None:
    """The copy-paste commands must not pin the previous image.

    SKILL.md is not documentation, it is the ClawHub listing: whatever image tag
    its `podman run` / `docker run` / MCP-config examples name is what a reader
    copies into their own setup. The frontmatter check above never looked at the
    body, and the body drifted — 0.8.1 shipped with three `:v0.8.0` examples in
    it, found only because someone read the listing before publishing it.

    `docs/` was added after the 0.8.4 release audit found six more image tags in
    `INSTALL.md` guarded by nothing at all. They are the same class as the
    SKILL.md ones and worse in reach: INSTALL.md is where the listing sends
    anyone who wants more than the one-liner.
    """
    expected = manifest_version()
    stale: list[str] = []
    seen_any = False

    for path in COPY_PASTE_SOURCES:
        if not path.exists():
            continue
        tags = IMAGE_TAG_RE.findall(path.read_text(encoding="utf-8"))
        if tags:
            seen_any = True
        stale += [
            f"{path.relative_to(REPO_ROOT)}: v{tag}" for tag in sorted(set(tags)) if tag != expected
        ]

    # Guard the guard: a regex that stopped matching would make every assertion
    # below vacuously true, and the examples cannot have vanished.
    assert seen_any, (
        "no wallet image tag found in any copy-paste source — the run examples "
        f"cannot have vanished from {[str(p.name) for p in COPY_PASTE_SOURCES]}"
    )
    assert not stale, (
        f"these copy-paste commands name an image other than {expected!r}, so a reader "
        "following them would run the previous wallet:\n  " + "\n  ".join(sorted(stale))
    )


# An image reference is unambiguous in a way prose is not: it always names what
# to run NOW, so any occurrence of this form outside the registry is either a
# point nobody counted or a lie waiting to be copied.
_IMAGE_ANYWHERE = re.compile(r"ghcr\.io/rustok-org/rustok-wallet-tui:v([0-9]+\.[0-9]+\.[0-9]+)")

_SWEEP_SKIP_DIRS = frozenset(
    {".git", ".venv", ".claude", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
)

# Files where an image reference is deliberately NOT the current version. Each
# entry is a decision with a reason, not a silencer — an exemption without one
# is how smithery.yaml would have been "handled".
_SWEEP_EXEMPT = {
    "tests/shim/run-tests.sh": (
        "a stub container from the v0.8.0 era, planted to prove the shim reads an "
        "existing registration; it is fixture data, not a place a release edits"
    ),
}


def _sweep_files() -> list[Path]:
    return sorted(
        path
        for path in REPO_ROOT.rglob("*")
        if path.is_file() and not _SWEEP_SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts)
    )


def test_no_image_reference_escapes_the_registry() -> None:
    """Nothing in this tree may name a wallet image other than the manifest's.

    The registry says which places are known. This says there are no others —
    the harder half, because a place nobody declared is exactly the one nobody
    bumps. `smithery.yaml` sat on v0.9.2 for eight releases: the Smithery
    storefront told people to run an image from three minor versions back, and
    no guard, no bump and no pair of eyes noticed. It was found by this sweep's
    pattern, not by reading.

    Scoped to the IMAGE form on purpose. The installer-URL form
    (`wallet-tui-vX.Y.Z`) cannot be swept the same way: `CHANGELOG.md` and
    `docs/CAVEATS.md` legitimately reference older releases by tag, and telling
    "the current one" from "the one where this changed" needs meaning, not a
    regex. That half stays held by `tests/test_docs_one_command.py` over a named
    list of docs, and its limit is written down in AGENTS.md rather than papered
    over.
    """
    expected = manifest_version()
    stale: list[str] = []
    seen = 0

    for path in _sweep_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for found in _IMAGE_ANYWHERE.findall(line):
                seen += 1
                if found == expected or relative in _SWEEP_EXEMPT:
                    continue
                stale.append(f"{relative}:{line_no}: names v{found}, manifest says {expected}")

    # Guard the guard: a pattern that stopped matching would make this vacuous,
    # and the run examples cannot have vanished from the tree.
    assert seen >= 10, (
        f"the sweep found only {seen} image references in the whole tree — the "
        "pattern has stopped matching what it is meant to watch"
    )
    assert not stale, (
        "these name a wallet image the manifest does not:\n  "
        + "\n  ".join(stale)
        + "\n\nEither bump them, add them to VERSION_POINTS, or exempt them with a reason."
    )


def test_every_sweep_exemption_is_still_earning_it() -> None:
    """An exemption outlives its reason silently — so it has to keep proving it.

    A file exempted because it carries a deliberately old tag, but which no
    longer carries one, is a hole left open for the next person to fall into.
    """
    expected = manifest_version()
    for relative, reason in _SWEEP_EXEMPT.items():
        path = REPO_ROOT / relative
        assert path.exists(), f"{relative} is exempt from the image sweep but does not exist"
        found = _IMAGE_ANYWHERE.findall(path.read_text(encoding="utf-8"))
        assert found, f"{relative} is exempt from the image sweep but names no image at all"
        assert any(version != expected for version in found), (
            f"{relative} is exempt because {reason}, but every image it names is now "
            f"{expected} — the exemption protects nothing and should be deleted"
        )
