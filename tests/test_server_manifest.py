"""`server.json` is a storefront, and nothing was reading it.

It is the MCP Registry manifest — a second listing, separate from ClawHub's
`claw.json`. This line's copy is correct today; the agent line's was not. Between
0.4.3 and 0.4.5 that one announced `version: 0.4.4` next to an image identifier
of `v0.4.2`, disagreeing both with its package and with itself, three releases
running, and following it installed a wallet a month older than advertised.

Nothing read inside the file on either line. `test_claw_manifest.py` only checks
that `claw.json` is not a copy of this one; the version and the image it points
at were guarded by no one. This guard is here **before** the same drift happens
here — the 0.8.4 release audit found this file sitting outside every check.

The check deliberately reads `pyproject.toml` rather than a constant: a constant
would be one more version point to forget, which is the failure being prevented.
"""

import json
import re
from typing import Any

from tests.version_points import REPO_ROOT, manifest_version

SERVER_JSON = REPO_ROOT / "server.json"


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
