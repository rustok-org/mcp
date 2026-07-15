"""Acceptance (slow): a parked transaction expires when nobody decides.

This one waits out the real 15-minute pending TTL of the shipped image. There is no
faster honest way: the TTL comes from `PendingStore::with_default_ttls()` (core
`server.rs`), no environment variable overrides it, and `force_expire` is a
`#[cfg(test)]` hook that does not exist in the release build. Adding a knob to the core
would mean testing an image we never shipped — which would defeat the whole stage.

`expired` is not cosmetic: it is the state the agent's polling contract leans on, and
this is the only test that proves the deadline actually fires.
"""

from __future__ import annotations

import time

import pytest

from tests.e2e.console import Console
from tests.e2e.test_approval_e2e import RECIPIENT, SEND_WEI, wait_status
from tests.e2e.wallet import Wallet

pytestmark = pytest.mark.e2e_slow

# The shipped pending TTL, plus a minute of slack for the lazy sweep.
PENDING_TTL_SECONDS = 15 * 60
SLACK_SECONDS = 60


def test_s3_a_parked_transaction_expires_when_nobody_decides(wallet: Wallet) -> None:
    """S3: nobody approves -> the deadline fires -> the agent sees `expired`."""
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    # Take the deadline while the item is still pending: once it resolves, the core
    # reports `not_after_unix: 0` and the gateway serialises that as null (core
    # `approval.rs::view` / `gateway::execution_json`). Reading it after expiry would
    # prove nothing.
    parked = wallet.status(preview_id)
    assert parked["state"] == "pending"
    deadline_unix = parked["not_after_unix"]
    assert deadline_unix > time.time(), "a freshly parked item must carry a future deadline"

    time.sleep(PENDING_TTL_SECONDS + SLACK_SECONDS)

    # Expiry is swept lazily — the status call is what makes the core notice.
    expired = wait_status(wallet, preview_id, "expired", timeout=120)
    assert expired["tx_hash"] is None, "an expired transaction must never have been signed"
    assert expired["not_after_unix"] is None, (
        "a resolved entry drops its deadline (core reports 0, the gateway sends null)"
    )
    assert deadline_unix < time.time(), "the deadline the item was parked with must have passed"

    # The card is gone from the human's side too: an expired item is no longer live.
    # v0.2 home is the Dashboard — the "waiting for you" count says it directly.
    with Console(wallet.name) as console:
        console.wait_for_text("PIN")
        console.submit_pin(wallet.pin)
        console.wait_for_text("Waiting for you: nothing pending")
