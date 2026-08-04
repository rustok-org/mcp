"""The image we build ON must be named exactly, never by a floating tag.

`Dockerfile.wallet` pins the core it copies binaries out of. (The console line
pins a console image beside it; this line has no console.) These are **dependency pins**, not our own version — which is
why they sit outside `test_version_consistency.py` and why the release audit
found them guarded by nothing at all.

What this can check and what it cannot, stated plainly so the coverage is not
overread later:

* **Checked here — shape.** `:latest`, `:v0`, `:v0.3`, a bare repo with no tag,
  a digest with no version: all of them mean the bytes we build on can change
  under us between two builds of the same wallet version. That is the failure a
  reproducible release cannot tolerate, and it is decidable from the tree.
* **NOT checked here — staleness.** Whether `v0.3.2` is still the current core
  is not answerable inside this repository: there is no source of truth for the
  core's version here, and asking the registry would make this test advisory and
  network-bound. `v0.1.4` against a released `v0.1.5` passes this file. That
  class stays on the release checklist, and
  `meta/docs/RELEASE-IDENTITY-MAP.md` records it as half-closed rather than
  closed.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile.wallet"

# `ARG NAME=ghcr.io/owner/image:tag` — the tag is what we judge.
ARG_PIN_RE = re.compile(
    r"^ARG\s+(?P<name>[A-Z_]*IMAGE)=(?P<ref>\S+)$",
    re.MULTILINE,
)

# An exact release: v, then three numbers. `v0`, `v0.3` and `latest` are the
# floating tags this test exists to reject.
EXACT_TAG_RE = re.compile(r":v[0-9]+\.[0-9]+\.[0-9]+$")


def _pins() -> dict[str, str]:
    return {
        match.group("name"): match.group("ref")
        for match in ARG_PIN_RE.finditer(DOCKERFILE.read_text(encoding="utf-8"))
    }


def test_the_dockerfile_declares_its_dependency_pins() -> None:
    """Guard the guard: no pins found would make the check below vacuous."""
    pins = _pins()
    assert pins, (
        f"no ARG *_IMAGE pin found in {DOCKERFILE.name} — either the build stopped "
        "declaring what it builds on, or this test stopped being able to see it. "
        "Both are worth failing over."
    )


@pytest.mark.parametrize("name", sorted(_pins()))
def test_every_dependency_pin_names_an_exact_version(name: str) -> None:
    """A floating dependency tag makes the same wallet version build differently."""
    ref = _pins()[name]
    assert EXACT_TAG_RE.search(ref), (
        f"{name}={ref!r} is not pinned to an exact version. A floating tag "
        "(`latest`, `:v0`, `:v0.3`) lets the bytes we build on change between two "
        "builds of the same wallet version, so the image a user gets stops being "
        "decided by this repository. Pin it as :vX.Y.Z."
    )
