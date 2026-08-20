"""Keep every place that names the wallet version telling the same story.

The list of those places is not here — it is declared once in
`tests/version_points.py`, because it used to live in this file's local
dictionary while the *count* lived in prose beside it, and the two drifted apart
in 0.11.0: the prose said six, the release found ten the hard way, and nothing
noticed until a human did.

One version, 8 homes — a mismatch blocks the release, strands users, or makes
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
