"""Fixtures for the agent-line acceptance suite: the image under test."""

from __future__ import annotations

import os
import shutil

import pytest

from tests.e2e.podman import podman

# The suite aims at the SHIPPED artifact — override to accept a different tag:
#   RUSTOK_E2E_IMAGE=ghcr.io/rustok-org/rustok-wallet:v0.4.1 uv run pytest -m e2e
DEFAULT_IMAGE = "ghcr.io/rustok-org/rustok-wallet:v0.4.2"


@pytest.fixture(scope="session")
def image() -> str:
    """The wallet image under acceptance; the suite is meaningless without it."""
    if shutil.which("podman") is None:
        pytest.skip("acceptance needs podman (not available on this machine)")
    img = os.environ.get("RUSTOK_E2E_IMAGE", DEFAULT_IMAGE)
    if podman("image", "exists", img, check=False).returncode != 0:
        pytest.skip(f"acceptance image not present locally: {img}")
    return img
