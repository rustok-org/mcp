"""Part A of the two-part guard: ask the shipped image what it does about signing.

Nine published texts said `sign_message` returns a signature without the console
approval window. The wallet refuses it outright — in every mode, since core
v0.4.0 — and no amount of reading our own documents could have shown that,
because a document is not a witness to behaviour, not even our own. Only the
call is. So this test makes the call.

It is the live half of a pair. `tests/test_the_texts_match_the_wallet.py` guards
that the texts carry the true sentence; it cannot know whether that sentence is
true. This one knows, and never reads a text. Restore the false sentence and the
other half goes red; land signature parking (`kind:sign`, increment 3) without
touching the texts and THIS one goes red. Neither is worth much alone.

Two deliberate departures from its siblings in this suite, both load-bearing:

* **The image comes from `WALLET_DIGEST`, not from the version tag.** Siblings
  resolve `ghcr.io/…:v{manifest_version}` (`conftest.py:33`), which is right for
  them: they accept the release. This one asks whether the texts match *what a
  user runs*, and a user runs the digest the installer pins. A tag is a name that
  can be repointed; a digest is the bytes.
* **No chain fixture.** Anvil exists so a sibling can broadcast and read a
  transaction back. A refusal happens before anything reaches a network, so
  pulling in a node would buy nothing and couple this guard to unrelated
  infrastructure.

Release-order caveat: on a release that actually changes signing, the text flip
has to ride in the digest-pin PR. During prep `WALLET_DIGEST` still names the
previous image, so a text that got ahead of the bytes turns this red mid-chain.
"""

import re
import uuid
from pathlib import Path

import pytest

from .mcp_client import McpStdio
from .podman import podman, volume_rm
from .wallet import KEYRING_PASSWORD

REPO_ROOT = Path(__file__).parent.parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
IMAGE_REPO = "ghcr.io/rustok-org/rustok-wallet-tui"

# What the core answers. Matched on the stable half — the parenthetical
# ("proto 3, increment 3") is a roadmap note and will move.
REFUSAL = re.compile(r"blocked by policy|sign parking arrives", re.IGNORECASE)


def _pinned_image() -> str:
    """The exact bytes this tree ships — the reference a user's installer pulls."""
    match = re.search(r'^WALLET_DIGEST="([^"]+)"$', INSTALL_SH.read_text(), re.MULTILINE)
    assert match, "install.sh carries no WALLET_DIGEST — nothing to hold the texts against"
    digest = match.group(1)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), (
        f"WALLET_DIGEST is not a usable digest: {digest!r}. During release prep it is "
        "the previous release's — that is expected; a placeholder or a malformed value "
        "is not, and this guard cannot run against it."
    )
    return f"{IMAGE_REPO}@{digest}"


@pytest.mark.e2e
def test_the_shipped_wallet_refuses_to_sign_a_message(tmp_path: Path) -> None:
    """`sign_message` is refused, so every text that describes it must say so."""
    image = _pinned_image()
    volume = f"rustok-e2e-signing-{uuid.uuid4().hex[:12]}"
    podman("volume", "create", volume)
    try:
        podman(
            "run",
            "--rm",
            "-v",
            f"{volume}:/data",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
            image,
            "create-wallet",
        )
        client = McpStdio(
            [
                "podman",
                "run",
                "-i",
                "--rm",
                "-v",
                f"{volume}:/data",
                "-e",
                f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
                image,
            ],
            tmp_path / "wallet-stderr.log",
        )
        try:
            client.initialize()
            with pytest.raises(RuntimeError) as refusal:
                client.call(
                    "tools/call",
                    {"name": "sign_message", "arguments": {"message": "probe"}},
                )
        finally:
            client.close()
    finally:
        volume_rm(volume)

    assert REFUSAL.search(str(refusal.value)), (
        f"sign_message did not refuse — it answered: {refusal.value}\n"
        "If signature parking has landed, this guard has done its job: the wallet's "
        "behaviour changed and the texts describing it are now stale. Update them "
        "(SKILL.md, claw.json, DISCLAIMER.md, docs/CAVEATS.md) in the same change."
    )
