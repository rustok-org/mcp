"""Guard the ClawHub skill manifest shape.

Regression guard for the Stage 4 defect where skills/rustok-wallet/claw.json
was overwritten wholesale with server.json (MCP-registry schema) and green CI
never noticed: the two manifests serve different registries and must not be
mixed up again.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
CLAW_PATH = REPO_ROOT / "skills" / "rustok-wallet-tui" / "claw.json"

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


def _load_claw() -> dict[str, Any]:
    return json.loads(CLAW_PATH.read_text())


def test_claw_manifest_carries_all_clawhub_keys() -> None:
    """Every ClawHub manifest field from the 0.4.4 baseline must be present."""
    claw = _load_claw()
    assert claw.keys() >= CLAWHUB_REQUIRED_KEYS


def test_claw_manifest_is_not_a_server_json_clone() -> None:
    """MCP-registry schema fields must never leak into the ClawHub manifest."""
    claw = _load_claw()
    assert not (SERVER_JSON_ONLY_KEYS & claw.keys())
    # The ClawHub listing slug, not the MCP-registry reverse-DNS name.
    assert claw["name"] == "rustok-wallet-tui"


def test_claw_manifest_entry_file_exists() -> None:
    """The entry pointer must reference a real file next to the manifest."""
    claw = _load_claw()
    assert (CLAW_PATH.parent / claw["entry"]).is_file()


def test_claw_manifest_version_matches_pyproject() -> None:
    """ClawHub uploads require the manifest version to track the release."""
    claw = _load_claw()
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    assert claw["version"] == pyproject["project"]["version"]


def test_claw_and_skill_descriptions_stay_identical() -> None:
    """The storefront copy is written twice — it must not drift.

    `claw.json` feeds the ClawHub listing and the SKILL.md frontmatter feeds the
    agent's own view of the skill; both are the same sentence about what this
    wallet does and does not protect. Nothing forced them to agree until now, so
    editing one and forgetting the other would ship a listing that promises
    something the skill itself does not say.
    """
    claw_description = _load_claw()["description"]
    # Read the frontmatter line directly rather than through a YAML parser:
    # PyYAML is only present here transitively and is not a declared dependency.
    skill_text = (CLAW_PATH.parent / "SKILL.md").read_text()
    match = re.search(r"^description: (.+)$", skill_text, re.MULTILINE)
    assert match, "SKILL.md frontmatter has no description line"
    skill_description = match.group(1)
    assert claw_description == skill_description, (
        "claw.json and SKILL.md describe the skill differently — the storefront "
        "and the agent must be told the same thing"
    )
