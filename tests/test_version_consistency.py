"""Keep every place that names the wallet version telling the same story.

The version is not written once — it is written in five places that must agree:
the package manifest, the skill frontmatter, the ClawHub manifest, the version
the installer reports, and the image tag the shim launches. They drift silently,
and a drift is not cosmetic here:

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


def _first_match(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name}: no version found for pattern {pattern!r}"
    return match.group(1)


def manifest_version() -> str:
    # Same extraction the publish workflow uses for its own gate: first
    # top-level `version = "..."`.
    return _first_match(PYPROJECT, r'^version = "(.+)"$')


def test_every_version_point_matches_the_manifest() -> None:
    """One version, five homes — a mismatch blocks the release or strands users."""
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
    }
    drifted = [
        f"{where}: {value!r} != {expected!r}" for where, value in found.items() if value != expected
    ]
    assert not drifted, (
        f"version drift against pyproject.toml ({expected!r}) — the publish workflow's "
        "own gate rejects a mismatched manifest, and a stale image tag strands users "
        "on an old wallet:\n  " + "\n  ".join(drifted)
    )
