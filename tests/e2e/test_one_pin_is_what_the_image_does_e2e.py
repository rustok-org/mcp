"""The live half of the one-PIN guard: ask the shipped image whether it takes the
PIN the person chose.

`tests/test_the_texts_say_one_pin.py` holds every published text to the new
description — you choose the PIN at `rustok init`, the phrase is the one backup,
`restore` brings the same address back. It cannot know whether any of that is
true: a text has no feature that separates a right description of behaviour
from a wrong one. This test knows, and never reads a text.

The pair exists because the 0.10.0 release walked over the checklist's own
rule: the texts moved two PRs before the bytes did, and nothing went red,
because the only live guard in the suite (`test_signing_is_refused_e2e.py`)
asks about signing. Had `create-wallet` shipped without reading stdin, every
INSTALL.md sentence would have described a wallet that does not exist, and the
suite would have said green.

Same two departures as its sibling, for the same reasons: the image comes from
`WALLET_DIGEST` (the bytes a user's installer pulls, not a tag that can be
repointed), and no chain fixture (nothing here reaches a network).

Release-order caveat, inherited: on a release that changes this flow, the text
flip rides in the digest-pin PR. During prep `WALLET_DIGEST` still names the
previous image, so a text that got ahead of the bytes turns this red mid-chain
— which is the guard doing its job, not a reason to silence it.
"""

import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from .podman import PODMAN, podman, volume_rm
from .wallet import KEYRING_PASSWORD

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
IMAGE_REPO = "ghcr.io/rustok-org/rustok-wallet-tui"

# The keyring password stays a file/env matter — only what a person TYPES moved
# to stdin. `KEYRING_PASSWORD` is the suite's throwaway value (`wallet.py`).

# The BIP-39 reference vector and the address every MetaMask-compatible wallet
# derives for it on m/44'/60'/0'/0/0. A known answer, not a self-comparison.
ABANDON_12 = (
    "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
)
ABANDON_12_ADDRESS = "0x9858EfFD232B4033E47d90003D41EC34EcaEda94"

CHOSEN = re.compile(r"the one you just chose", re.IGNORECASE)
MINTED = re.compile(r"Transaction-approval PIN", re.IGNORECASE)


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


def _one_shot(
    image: str, volume: str, subcommand: str, stdin: str
) -> subprocess.CompletedProcess[str]:
    """Run a one-shot core command in the shipped image with `stdin` on its pipe.

    `-i`, never `-it`: the PIN travels on the pipe, and a pty on top of a pipe is
    not a thing. The banners the core prints go to stderr and need no tty.
    """
    return subprocess.run(
        [
            PODMAN,
            "run",
            "-i",
            "--rm",
            "-v",
            f"{volume}:/data",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
            image,
            subcommand,
        ],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


NEEDS_PODMAN = pytest.mark.skipif(
    shutil.which("podman") is None,
    reason=(
        "needs podman to ask the shipped image — a silent non-selection would let "
        "the texts drift from the bytes, which is the one thing this test exists to catch"
    ),
)


@pytest.mark.e2e
@NEEDS_PODMAN
def test_the_shipped_wallet_takes_the_pin_the_person_chose() -> None:
    image = _pinned_image()
    volume = f"rustok-e2e-onepin-{uuid.uuid4().hex[:12]}"
    podman("volume", "create", volume)
    try:
        chosen = _one_shot(image, volume, "create-wallet", "402913\n")
    finally:
        volume_rm(volume)

    assert chosen.returncode == 0, f"create-wallet failed:\n{chosen.stderr}"
    assert CHOSEN.search(chosen.stderr), (
        "the shipped image did not acknowledge a chosen PIN — it printed:\n"
        f"{chosen.stderr}\n"
        "Every INSTALL/SKILL sentence says the person chooses the PIN at `rustok init`. "
        "If the image mints instead, the texts describe a wallet that does not exist: "
        "either the pinned digest is behind the texts (release order — the text flip "
        "belongs in the digest-pin PR) or the core regressed."
    )
    assert not MINTED.search(chosen.stderr), (
        "a chosen PIN must not come back as a minted one:\n" + chosen.stderr
    )
    assert "402913" not in chosen.stderr and "402913" not in chosen.stdout, (
        "the chosen PIN was echoed by the image — it must appear on neither stream:\n"
        + chosen.stderr
    )


@pytest.mark.e2e
@NEEDS_PODMAN
def test_the_shipped_wallet_still_mints_when_nothing_is_offered() -> None:
    """Positive control for the test above, and the no-shim path's contract.

    With nothing on stdin the image mints and prints — so stderr is a channel a
    PIN CAN travel on, and 'a chosen PIN is not printed' means something. It is
    also what `create-wallet` run by hand (INSTALL appendix) is promised.
    """
    image = _pinned_image()
    volume = f"rustok-e2e-onepin-mint-{uuid.uuid4().hex[:12]}"
    podman("volume", "create", volume)
    try:
        minted = _one_shot(image, volume, "create-wallet", "")
    finally:
        volume_rm(volume)

    assert minted.returncode == 0, f"create-wallet (no stdin) failed:\n{minted.stderr}"
    assert MINTED.search(minted.stderr), (
        "with nothing on stdin the image must mint and print a PIN — the by-hand path "
        "in INSTALL promises it, and this test's sibling relies on it as a positive "
        "control:\n" + minted.stderr
    )


@pytest.mark.e2e
@NEEDS_PODMAN
def test_the_shipped_wallet_restores_the_reference_phrase_to_its_address() -> None:
    """`rustok restore` is the backup the texts promise; the address is the proof.

    A phrase in, the address every other BIP-39 wallet derives for it out — or
    the person's funds sit somewhere else and 'the 12 words are your backup' is
    a sentence, not a fact.
    """
    image = _pinned_image()
    volume = f"rustok-e2e-onepin-restore-{uuid.uuid4().hex[:12]}"
    podman("volume", "create", volume)
    try:
        restored = _one_shot(image, volume, "restore-wallet", f"{ABANDON_12}\n715048\n")
    finally:
        volume_rm(volume)

    assert restored.returncode == 0, f"restore-wallet failed:\n{restored.stderr}"
    assert ABANDON_12_ADDRESS in restored.stderr, (
        "restore-wallet did not bring the reference phrase back to its address. "
        f"Expected {ABANDON_12_ADDRESS}, got:\n{restored.stderr}"
    )
    assert "abandon" not in restored.stderr and "abandon" not in restored.stdout, (
        "the phrase was echoed by the image — it must appear on neither stream"
    )
    assert CHOSEN.search(restored.stderr), "restore takes the chosen PIN too:\n" + restored.stderr
