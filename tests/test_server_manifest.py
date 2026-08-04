"""`server.json` is a storefront, and nothing was reading it.

It is the MCP Registry manifest — a second listing, separate from ClawHub's
`claw.json`. Between 0.4.3 and 0.4.5 it drifted twice over and nobody noticed:
it announced `version: 0.4.4` next to an image identifier of `v0.4.2`, so the
file disagreed both with the package and with itself, three releases running.

Nothing read inside it. `test_claw_manifest.py` only checks that `claw.json` is
not a copy of this file; the version and the image it points at were guarded by
no one. These two tests are that guard.

The check deliberately reads `pyproject.toml` rather than a constant: a constant
would be one more version point to forget, which is the failure being fixed.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
SERVER_JSON = REPO_ROOT / "server.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def manifest_version() -> str:
    """The single source of truth every other version point answers to."""
    return str(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])


def _server() -> dict[str, Any]:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_server_manifest_version_matches_the_package() -> None:
    """A registry listing that announces the wrong version misdirects installs."""
    expected = manifest_version()
    found = _server()["version"]
    assert found == expected, (
        f"server.json says version {found!r} but pyproject.toml says {expected!r}. "
        "This file is the MCP Registry listing — a second storefront — and it has "
        "drifted silently before."
    )


def test_server_manifest_image_tag_matches_the_package() -> None:
    """The OCI identifier is what a reader actually pulls.

    This is the half that rotted worst: the version field was one release behind
    while the image was three, so following the listing installed a wallet from
    a month earlier than the listing claimed.
    """
    expected = manifest_version()
    packages = _server()["packages"]
    oci = [p for p in packages if p.get("registryType") == "oci"]
    assert oci, "server.json declares no OCI package — the listing installs nothing"

    stale = []
    for package in oci:
        identifier = package["identifier"]
        match = re.search(r":v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$", identifier)
        if match is None:
            stale.append(f"{identifier!r} does not end in a :vX.Y.Z tag")
        elif match.group("version") != expected:
            stale.append(f"{identifier!r} is not v{expected}")

    assert not stale, (
        "server.json points at an image that is not this release:\n  "
        + "\n  ".join(stale)
        + f"\npyproject.toml says {expected!r}."
    )
