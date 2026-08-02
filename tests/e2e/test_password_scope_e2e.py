"""Acceptance: the keyring password reaches core and no one else.

Core is the only process that needs the password, and it needs it once — it reads
the variable at startup, unlocks the keystore, and never looks again
(`core/crates/grpc/src/main.rs`). The gateway and the Python MCP server never read
it at all. Until v0.4.2 the entrypoint nevertheless exported it to every child, so
the process that parses untrusted input — LLM tool arguments, third-party RPC
answers — carried the wallet password in its own environment, and so did anything
it spawned.

What this suite proves, and only this: after the entrypoint drops the variable,
the password is absent from the environment of the MCP server and the gateway,
while the wallet still unlocks and serves. What it deliberately does NOT claim:
that the password is unreachable. Core's `/proc/<pid>/environ` still holds it and
stays readable to the same uid — `PR_SET_DUMPABLE` does not survive `execve`
(measured), and core on the frozen v0.1.x line sets no such flag itself. That gap
closes only inside core; see docs/TROUBLESHOOTING.md.

Redaction discipline, as in `test_password_file_e2e`: no raw container output may
reach a failure message — `create_wallet` output carries the recovery phrase.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from tests.e2e.podman import podman, rm_force, volume_rm
from tests.e2e.wallet import KEYRING_PASSWORD, create_wallet

pytestmark = pytest.mark.e2e

# Processes that handle untrusted input. Neither reads the password in code
# (0 occurrences of RUSTOK_KEYRING_PASSWORD in the gateway crate and in src/).
UNTRUSTED = ("rustok-mcp-stdi", "gateway")

# One shell probe, run inside the container: for every live pid, report the comm
# of any process whose own environment still carries the keyring password.
LEAK_PROBE = r"""
for p in /proc/[0-9]*; do
    if tr '\0' '\n' < "$p/environ" 2>/dev/null | grep -q '^RUSTOK_KEYRING_PASSWORD='; then
        cat "$p/comm" 2>/dev/null
    fi
done
"""


@pytest.fixture
def running_wallet(image: str) -> Iterator[str]:
    """A started wallet container, torn down with its volume."""
    suffix = uuid.uuid4().hex[:8]
    name, volume = f"rustok-scope-{suffix}", f"rustok-scope-vol-{suffix}"
    try:
        create_wallet(image, volume)
        podman(
            "run",
            "-d",
            "--name",
            name,
            "-i",
            "-v",
            f"{volume}:/data",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
            image,
        )
        _wait_for_core(name)
        # The entrypoint `exec`s the MCP server only after the gateway reports
        # ready, so a probe fired at that moment can miss it and read as a pass.
        # Wait for the process itself, not for a duration.
        _wait_for_process(name, "rustok-mcp-stdi")
        yield name
    finally:
        rm_force(name)
        volume_rm(volume)


def _wait_for_core(name: str) -> None:
    """Block until the gateway reports core serving, or fail the test."""
    probe = (
        "import urllib.request,sys,time\n"
        "for _ in range(60):\n"
        "    try:\n"
        '        if b\'"core":"serving"\' in urllib.request.urlopen('
        "'http://127.0.0.1:3000/health', timeout=2).read(): sys.exit(0)\n"
        "    except Exception: pass\n"
        "    time.sleep(1)\n"
        "sys.exit(1)\n"
    )
    result = podman("exec", name, "python", "-c", probe, check=False)
    if result.returncode != 0:
        pytest.fail("wallet never reported core serving — unlock path is broken")


def _wait_for_process(name: str, comm: str) -> None:
    """Block until a process with this `comm` exists in the container, or fail."""
    probe = f"for _ in $(seq 60); do grep -qx '{comm}' /proc/[0-9]*/comm 2>/dev/null && exit 0; sleep 1; done; exit 1"
    if podman("exec", name, "sh", "-c", probe, check=False).returncode != 0:
        pytest.fail(f"process {comm!r} never appeared — the container never finished starting")


def _processes_holding_password(name: str) -> set[str]:
    out = podman("exec", name, "sh", "-c", LEAK_PROBE).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_untrusted_processes_do_not_carry_the_password(running_wallet: str) -> None:
    """The MCP server and the gateway must not hold the password in their env.

    Red against v0.4.2, where the entrypoint exported it to every child.
    """
    holders = _processes_holding_password(running_wallet)
    leaked = sorted(h for h in holders if h in UNTRUSTED)
    assert not leaked, (
        f"processes handling untrusted input still carry the keyring password: {leaked}"
    )


def test_core_still_carries_it(running_wallet: str) -> None:
    """Positive control: the probe can see a password when one is there.

    Without this, `test_untrusted_processes_do_not_carry_the_password` would also
    pass against a broken probe that never finds anything.
    """
    holders = _processes_holding_password(running_wallet)
    assert "core-server" in holders, (
        "probe found the password nowhere at all — it is not measuring what it claims"
    )
