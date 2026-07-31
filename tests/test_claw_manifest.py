"""Guard the ClawHub skill manifest shape (agent line).

Regression guard, adapted from the console line's `test_claw_manifest.py`: the two
manifests (`claw.json` for ClawHub, `server.json` for the MCP registry) serve
different registries and must not be mixed up. Unlike the console line, the
agent line's skill version and package version are INDEPENDENT by design (the
skill has been re-published on ClawHub more times than the package has shipped)
— so this file does NOT assert `claw.json` version == `pyproject.toml` version.
It asserts `claw.json` version == the `SKILL.md` frontmatter version instead:
those two must always travel together, since ClawHub renders one from the other.
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "rustok-wallet"
CLAW_PATH = SKILL_DIR / "claw.json"
SKILL_MD_PATH = SKILL_DIR / "SKILL.md"

CLAWHUB_REQUIRED_KEYS = {
    "name",
    "version",
    "description",
    "author",
    "license",
    "permissions",
    "entry",
    "tags",
    "minOpenClawVersion",
    "homepage",
}
SERVER_JSON_ONLY_KEYS = {"$schema", "packages", "websiteUrl", "repository"}

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _load_claw() -> dict[str, Any]:
    return json.loads(CLAW_PATH.read_text())


def _load_skill_frontmatter() -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(SKILL_MD_PATH.read_text())
    assert match, "SKILL.md must open with a --- ... --- YAML frontmatter block"
    return yaml.safe_load(match.group(1))


def test_claw_manifest_carries_all_clawhub_keys() -> None:
    """Every ClawHub manifest field must be present."""
    claw = _load_claw()
    assert claw.keys() >= CLAWHUB_REQUIRED_KEYS


def test_claw_manifest_is_not_a_server_json_clone() -> None:
    """MCP-registry schema fields must never leak into the ClawHub manifest."""
    claw = _load_claw()
    assert not (SERVER_JSON_ONLY_KEYS & claw.keys())
    assert claw["name"] == "rustok-wallet"


def test_claw_manifest_entry_file_exists() -> None:
    """The entry pointer must reference a real file next to the manifest."""
    claw = _load_claw()
    assert (CLAW_PATH.parent / claw["entry"]).is_file()


def test_claw_manifest_version_matches_skill_frontmatter() -> None:
    """claw.json and SKILL.md frontmatter must ship the same version.

    Not pinned to pyproject.toml — the skill and the package version
    independently on this line (see module docstring).
    """
    claw = _load_claw()
    frontmatter = _load_skill_frontmatter()
    assert claw["version"] == frontmatter["version"]
