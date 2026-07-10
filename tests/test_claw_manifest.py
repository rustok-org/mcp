"""Guard the ClawHub skill manifest shape.

Regression guard for the Stage 4 defect where skills/rustok-wallet/claw.json
was overwritten wholesale with server.json (MCP-registry schema) and green CI
never noticed: the two manifests serve different registries and must not be
mixed up again.
"""

import json
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
