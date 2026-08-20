"""Keep every place that names the wallet version telling the same story.

The version is not written once — it is written in ten places that must agree,
six of them held by this file (the other four: see the docstring below):
the package manifest, the skill frontmatter, the ClawHub manifest, the version
the installer reports, the image tag the shim launches, and — since 0.9.3 — the
number the image states about itself for the console's identity panel. They
drift silently, and a drift is not cosmetic here:

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
rewritten every release. This test is green before and after a bump — its red
proof comes from mutation (desynchronise one point and it names that point).
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PYPROJECT = REPO_ROOT / "pyproject.toml"
SKILL_MD = REPO_ROOT / "skills" / "rustok-wallet-tui" / "SKILL.md"
CLAW_JSON = REPO_ROOT / "skills" / "rustok-wallet-tui" / "claw.json"
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
SHIM = REPO_ROOT / "cli" / "rustok"
DOCKERFILE = REPO_ROOT / "Dockerfile.wallet"


def _first_match(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name}: no version found for pattern {pattern!r}"
    return match.group(1)


def manifest_version() -> str:
    # Same extraction the publish workflow uses for its own gate: first
    # top-level `version = "..."`.
    return _first_match(PYPROJECT, r'^version = "(.+)"$')


def test_every_version_point_matches_the_manifest() -> None:
    """One version, six of its ten homes — a mismatch blocks the release, strands
    users, or makes the panel that answers "what am I running" answer wrong.

    Six is what THIS test holds. The 0.11.0 release found four more the hard way,
    each guarded elsewhere and none of them here: `server.json` carries the
    version and an image tag (`test_server_manifest.py`), the installer tag is
    pinned in `test_docs_one_command.py`, seven byte-exact registration lines in
    `tests/shim/run-tests.sh` carry the image, and `docs/TROUBLESHOOTING.md`
    repeats the installer URL. Bump the six here and four tests elsewhere go red;
    the count in this sentence is what a reader plans the release against."""
    expected = manifest_version()
    found = {
        "skills/rustok-wallet-tui/SKILL.md (frontmatter)": _first_match(
            SKILL_MD, r"^version: (.+)$"
        ),
        "skills/rustok-wallet-tui/claw.json": json.loads(CLAW_JSON.read_text(encoding="utf-8"))[
            "version"
        ],
        "scripts/install.sh (WALLET_VERSION)": _first_match(INSTALL_SH, r'^WALLET_VERSION="(.+)"$'),
        "cli/rustok (DEFAULT_IMAGE tag)": _first_match(
            SHIM, r'^DEFAULT_IMAGE="ghcr\.io/rustok-org/rustok-wallet-tui:v(.+)"$'
        ),
        # Sixth home, added in 0.9.3: the number the built image states about
        # itself, which the console reads and shows to a human. A drift here is
        # the quietest of the six — nothing refuses to build, nothing strands a
        # user, the panel simply says the wrong thing to the one person who
        # opened it to find out what they are running.
        "Dockerfile.wallet (ARG WALLET_VERSION)": _first_match(
            DOCKERFILE, r"^ARG WALLET_VERSION=(.+)$"
        ),
    }
    drifted = [
        f"{where}: {value!r} != {expected!r}" for where, value in found.items() if value != expected
    ]
    assert not drifted, (
        f"version drift against pyproject.toml ({expected!r}) — the publish workflow's "
        "own gate rejects a mismatched manifest, and a stale image tag strands users "
        "on an old wallet:\n  " + "\n  ".join(drifted)
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
