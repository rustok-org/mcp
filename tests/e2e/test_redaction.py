"""The onboarding output must never reach a failure message — a guard, not a demo.

`create-wallet` prints the 12-word recovery phrase and the approval PIN to stderr, and
this suite's log is pasted whole into the acceptance report. Every failure path out of
`create_wallet()` therefore has to be redacted: a wrong exit code, a format drift, or a
container that printed the banner and then hung.

These tests need no podman — they fake the process result — so they run in the DEFAULT
suite: the invariant is guarded on every commit, not only when someone runs acceptance.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from tests.e2e import wallet as wallet_module

# What a real onboarding banner looks like. If any of this survives into an error
# message, a fundable wallet has been published.
MNEMONIC = "animal travel drift smile coffee route robot rescue bread involve mandate appear"
PIN = "915910"
BANNER = (
    "\n======================  NEW AGENT WALLET  ======================\n"
    "Address:  0xcc75E0380b665037a6F9868F5545ea584Fe20ADd\n"
    "\nRecovery phrase (12 words) — WRITE IT DOWN, SHOWN ONLY ONCE:\n"
    f"\n    {MNEMONIC}\n"
    "\nTransaction-approval PIN (enter it in the wallet console) — WRITE IT DOWN:\n"
    f"\n    {PIN}\n"
)


def assert_no_secrets(message: str) -> None:
    """The failure message may not carry the phrase, the PIN, or any word of the phrase."""
    assert MNEMONIC not in message
    assert PIN not in message
    for word in MNEMONIC.split():
        assert word not in message, f"a word of the recovery phrase leaked: {word!r}"
    assert "redacted" in message, "a redacted failure must say so"


def test_a_failed_create_wallet_never_puts_the_recovery_phrase_in_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container printed the banner, then exited non-zero."""

    def crashed(*_args: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["podman"], returncode=125, stdout="", stderr=BANNER
        )

    monkeypatch.setattr(wallet_module, "podman", crashed)

    with pytest.raises(AssertionError) as failure:
        wallet_module.create_wallet("image", "network", "volume")

    assert_no_secrets(str(failure.value))


def test_a_hung_create_wallet_never_puts_the_recovery_phrase_in_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container printed the banner, then hung until the timeout killed it.

    `subprocess.TimeoutExpired` carries the captured stderr as an attribute, so this path
    hands the phrase to anything that renders the exception or its context.
    """

    def hung(*_args: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["podman"], timeout=120, output="", stderr=BANNER)

    monkeypatch.setattr(wallet_module, "podman", hung)

    with pytest.raises(AssertionError) as failure:
        wallet_module.create_wallet("image", "network", "volume")

    assert_no_secrets(str(failure.value))
    # The original exception carries the banner in `.stderr`: it must not be chained in
    # as `__cause__`/`__context__`, or a traceback renderer would walk right back to it.
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
