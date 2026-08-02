"""Acceptance: a freshly created wallet is handed twelve words, not twenty-four.

Twelve is the project standard and the BIP-39 default — 128 bits of entropy, out
of reach of brute force, and half as many words to copy down by hand. Hand
transcription is where recovery phrases are actually lost, so the shorter phrase
is the safer one in practice.

The v0.1.x core shipped in this line was the last production path still on 24.
This suite pins the outcome so a future edit cannot quietly drift back: it counts
the words in the phrase itself rather than reading the "(N words)" printed in the
banner, because the banner is a string and the phrase is the behaviour.

Redaction discipline, as everywhere in this suite: the phrase never reaches a
return value or a failure message — only its length does.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from tests.e2e.podman import volume_rm
from tests.e2e.wallet import create_wallet_phrase_word_count

pytestmark = pytest.mark.e2e

EXPECTED_WORDS = 12


@pytest.fixture
def fresh_volume() -> Iterator[str]:
    """An empty volume, removed afterwards along with the throwaway keystore."""
    volume = f"rustok-mnemonic-vol-{uuid.uuid4().hex[:8]}"
    try:
        yield volume
    finally:
        volume_rm(volume)


def test_new_wallet_is_given_twelve_words(image: str, fresh_volume: str) -> None:
    """Onboarding prints a 12-word phrase.

    Red against the wallet image built on core v0.1.2, which printed 24.
    """
    words = create_wallet_phrase_word_count(image, fresh_volume)
    assert words == EXPECTED_WORDS, (
        f"onboarding handed the user {words} words, expected {EXPECTED_WORDS} "
        "(phrase itself redacted)"
    )
