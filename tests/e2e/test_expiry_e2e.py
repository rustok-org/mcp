"""Acceptance (slow): a parked transaction expires when nobody decides.

The real-time scenario waits for the deadline advertised by the exact image.
The controlled-clock scenario advances only the container's monotonic clock,
leaving the candidate bytes and wall time unchanged. Neither changes core state
or calls a test-only expiry API.

`expired` is not cosmetic: it is the state the agent's polling contract leans on, and
this is the only test that proves the deadline actually fires.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.conftest import STARTING_BALANCE, Chain
from tests.e2e.console import Console
from tests.e2e.podman import podman, rm_force, volume_rm
from tests.e2e.test_approval_e2e import RECIPIENT, SEND_WEI, wait_status
from tests.e2e.wallet import Wallet, create_wallet, start_wallet

pytestmark = pytest.mark.e2e_slow

# The shipped pending TTL, plus a minute of slack for the lazy sweep.
PENDING_TTL_SECONDS = 30 * 60
SLACK_SECONDS = 60


@pytest.fixture
def expiry_wallet(request: pytest.FixtureRequest) -> tuple[Wallet, Path | None]:
    """Choose an equivalent clock route; real 30-minute waiting remains available."""
    if os.environ.get("RUSTOK_E2E_REAL_TIME") == "1" or sys.platform != "linux":
        return request.getfixturevalue("wallet"), None
    return request.getfixturevalue("clock_wallet")


def test_s3_a_parked_transaction_expires_when_nobody_decides(
    expiry_wallet: tuple[Wallet, Path | None], chain: Chain, image: str
) -> None:
    """S3: nobody approves -> the deadline fires -> the agent sees `expired`."""
    wallet, offset = expiry_wallet
    balance_before = chain.anvil.balance(RECIPIENT)
    nonce_before = chain.anvil.rpc("eth_getTransactionCount", [wallet.address, "pending"])
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    # Take the deadline while the item is still pending: once it resolves, the core
    # reports `not_after_unix: 0` and the gateway serialises that as null (core
    # `approval.rs::view` / `gateway::execution_json`). Reading it after expiry would
    # prove nothing.
    parked = wallet.status(preview_id)
    assert parked["state"] == "pending"
    deadline_unix = parked["not_after_unix"]
    assert deadline_unix > time.time(), "a freshly parked item must carry a future deadline"

    assert PENDING_TTL_SECONDS - 5 <= deadline_unix - time.time() <= PENDING_TTL_SECONDS
    if offset is None:
        time.sleep(max(0, deadline_unix - time.time()) + SLACK_SECONDS)
    else:
        inspected = json.loads(podman("inspect", wallet.name).stdout)[0]
        assert inspected["Image"].removeprefix("sha256:") == image.removeprefix("sha256:")
        monotonic, wall = clock_read(wallet)
        offset.write_text("1200\n")
        later_monotonic, later_wall = clock_read(wallet)
        assert 1200 <= later_monotonic - monotonic < 1210
        assert 0 <= later_wall - wall < 10, "wall time must not be advanced"
        assert wallet.status(preview_id)["state"] == "pending", "20 minutes is before the real TTL"
        offset.write_text("1805\n")

    # Expiry is swept lazily — the status call is what makes the core notice.
    expired = wait_status(wallet, preview_id, "expired", timeout=120)
    assert expired["tx_hash"] is None, "an expired transaction must never have been signed"
    assert expired["not_after_unix"] is None, (
        "a resolved entry drops its deadline (core reports 0, the gateway sends null)"
    )
    if offset is None:
        assert deadline_unix < time.time(), "the advertised deadline must have passed"
    assert chain.anvil.balance(RECIPIENT) == balance_before
    assert chain.anvil.rpc("eth_getTransactionCount", [wallet.address, "pending"]) == nonce_before

    # The card is gone from the human's side too: an expired item is no longer live.
    # v0.2 home is the Dashboard — the "waiting for you" count says it directly.
    with Console(wallet.name) as console:
        console.wait_for_text("PIN")
        console.submit_pin(wallet.pin)
        console.wait_for_text("Waiting for you: nothing pending")


@pytest.fixture
def clock_wallet(chain: Chain, image: str, tmp_path: Path) -> Iterator[tuple[Wallet, Path]]:
    """Same image, one isolated volume, a host-compiled monotonic clock fixture."""
    compiler = shutil.which("cc")
    assert compiler, "controlled Linux clock acceptance requires a C compiler"
    clock_dir = tmp_path / "clock"
    clock_dir.mkdir(mode=0o755)
    subprocess.run(  # noqa: S603 — fixed test fixture/compiler argv; no shell
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(Path(__file__).parent / "fixtures/clock.c"),
            "-ldl",
            "-o",
            str(clock_dir / "clock.so"),
        ],
        check=True,
        capture_output=True,
    )
    offset = clock_dir / "offset"
    offset.write_text("0\n")
    suffix = uuid.uuid4().hex[:8]
    name, volume = f"rustok-wallet-tui-clock-{suffix}", f"rustok-e2e-clock-{suffix}"
    podman("volume", "create", volume)
    try:
        address, pin = create_wallet(image, chain.network, volume)
        chain.anvil.set_balance(address, STARTING_BALANCE)
        client = start_wallet(
            image,
            chain.network,
            volume,
            name,
            chain.url_from_container,
            tmp_path / "wallet.stderr.log",
            capabilities="read_wallet,preview_tx,execute_tx",
            extra_args=(
                "-v",
                f"{clock_dir}:/run/wallet-clock:ro,Z",
                "-e",
                "LD_PRELOAD=/run/wallet-clock/clock.so",
            ),
        )
        try:
            yield Wallet(name, address, pin, client, volume), offset
        finally:
            client.close()
    finally:
        rm_force(name)
        volume_rm(volume)


def clock_read(wallet: Wallet) -> tuple[float, float]:
    result = json.loads(
        wallet.exec(
            "python3", "-c", "import json,time; print(json.dumps([time.monotonic(),time.time()]))"
        ).stdout
    )
    return result[0], result[1]
