"""Fixtures for the acceptance suite: a local chain, and one fresh wallet per test."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.e2e.chain import WEI_PER_ETH, Anvil
from tests.e2e.podman import free_port, network_rm, podman, rm_force, volume_rm
from tests.e2e.wallet import CHAIN_ID, Wallet, create_wallet, start_wallet

# The suite aims at the SHIPPED artifact — override to accept a different tag.
DEFAULT_IMAGE = "ghcr.io/rustok-org/rustok-wallet-tui:v0.7.0"
DEFAULT_ANVIL_IMAGE = "ghcr.io/foundry-rs/foundry:latest"
STARTING_BALANCE = 10 * WEI_PER_ETH


@dataclass
class Chain:
    """The local anvil node, addressable from both sides of the podman network."""

    anvil: Anvil
    network: str
    url_from_container: str


@pytest.fixture(scope="session")
def image() -> str:
    """The wallet image under acceptance."""
    return os.environ.get("RUSTOK_E2E_IMAGE", DEFAULT_IMAGE)


@pytest.fixture(scope="session")
def chain() -> Iterator[Chain]:
    """A local anvil: real signing and a real broadcast, without a real network.

    Published to localhost as well as to the podman network — the suite must reach the
    node to fund the wallet and to read the mined transaction back, and the host has no
    DNS for the network's container names.
    """
    suffix = uuid.uuid4().hex[:8]
    network = f"rustok-e2e-net-{suffix}"
    container = f"rustok-e2e-anvil-{suffix}"
    port = free_port()
    anvil_image = os.environ.get("RUSTOK_E2E_ANVIL_IMAGE", DEFAULT_ANVIL_IMAGE)

    podman("network", "create", network)
    try:
        podman(
            "run",
            "-d",
            "--name",
            container,
            "--network",
            network,
            "-p",
            f"127.0.0.1:{port}:8545",
            anvil_image,
            f"anvil --host 0.0.0.0 --chain-id {CHAIN_ID}",
            timeout=300,
        )
        anvil = Anvil(f"http://127.0.0.1:{port}")
        deadline = time.monotonic() + 60
        while not anvil.is_up():
            if time.monotonic() > deadline:
                logs = podman("logs", container, check=False).stderr
                raise AssertionError(f"anvil never came up.\n{logs}")
            time.sleep(0.5)

        yield Chain(
            anvil=anvil,
            network=network,
            url_from_container=f"http://{container}:8545",
        )
    finally:
        rm_force(container)
        network_rm(network)


@pytest.fixture
def wallet(chain: Chain, image: str, tmp_path: Path) -> Iterator[Wallet]:
    """A freshly onboarded wallet in its own container, volume and keystore.

    Funded on the local chain, so a parked transaction can actually be broadcast.
    """
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-tui-e2e-{suffix}"
    volume = f"rustok-e2e-data-{suffix}"

    podman("volume", "create", volume)
    try:
        address, pin = create_wallet(image, chain.network, volume)
        chain.anvil.set_balance(address, STARTING_BALANCE)

        mcp = start_wallet(
            image=image,
            network=chain.network,
            volume=volume,
            name=name,
            anvil_url=chain.url_from_container,
            stderr_path=tmp_path / f"{name}.stderr.log",
        )
        try:
            yield Wallet(name=name, address=address, pin=pin, mcp=mcp)
        finally:
            mcp.close()
    finally:
        rm_force(name)
        volume_rm(volume)
