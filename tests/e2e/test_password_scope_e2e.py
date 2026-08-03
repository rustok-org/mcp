"""Acceptance: the keyring password reaches core and no one else.

Core is the only process that needs the password, and it needs it once — it reads
the variable at startup, unlocks the keystore, and never looks again
(`core/crates/grpc/src/main.rs`). The gateway and the Python MCP server never read
it at all. Until v0.4.2 the entrypoint nevertheless exported it to every child, so
the process that parses untrusted input — LLM tool arguments, third-party RPC
answers — carried the wallet password in its own environment, and so did anything
it spawned.

Since 0.4.4 the claim is stronger, because the gap this file used to document has
been closed at its source. Core v0.1.4 reads the password from a *file*, so the
entrypoint no longer has to hand it over as a variable: it stages an `-e` password
into a 0600 file, drops the variable, gives core the path, and deletes the file
once the keystore is unlocked. `tini` stopped being a carrier too — the entrypoint
is PID 1 itself and hands that role over through `exec`, which is the only thing
that rewrites `/proc/1/environ`.

So what this suite now proves: with the password delivered the *old* way (`-e`),
no process in the settled container carries it in its own environment — core
included. What it still does NOT claim: that the value is gone from the machine.
The runtime keeps a copy in the container config (`podman inspect`), which nothing
inside the image can reach; the documented delivery is a mounted file, and then
even that copy is a path.

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

# A canary the container is started with. It exists for one reason: to prove the
# probe below can see a variable when one is really there. Until 0.4.4 that job
# was done by asserting core still carried the password — which stops working the
# moment the leak is fixed, and would have to be deleted exactly when the suite
# needs its control most.
CANARY_VAR = "RUSTOK_SCOPE_CANARY"
CANARY_VALUE = "probe-can-see-this"  # noqa: S105  (not a secret; a visibility marker)

# One shell probe, run inside the container: for every live pid, report the comm
# of any process whose own environment carries the named variable.
LEAK_PROBE_TEMPLATE = r"""
for p in /proc/[0-9]*; do
    if tr '\0' '\n' < "$p/environ" 2>/dev/null | grep -q '^{variable}='; then
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
            "-e",
            f"{CANARY_VAR}={CANARY_VALUE}",
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


def _processes_holding(name: str, variable: str) -> set[str]:
    probe = LEAK_PROBE_TEMPLATE.format(variable=variable)
    out = podman("exec", name, "sh", "-c", probe).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_no_process_carries_the_password(running_wallet: str) -> None:
    """Not one process — core included — holds the password in its environment.

    Delivered the OLD way (`-e`), which is the hard case: the value really did
    enter the container as a variable. Red against v0.4.3, where the probe found
    `tini` and `core-server`; the untrusted pair was already clean by then.
    """
    holders = sorted(_processes_holding(running_wallet, "RUSTOK_KEYRING_PASSWORD"))
    assert holders == [], f"processes still carrying the keyring password: {holders}"


def test_the_probe_can_see_a_variable_that_is_really_there(running_wallet: str) -> None:
    """Positive control, independent of the defect under test.

    Without it, the assertion above would pass just as happily against a probe
    that finds nothing anywhere. The canary is delivered exactly like the old
    password was — a plain `-e` — so a probe that misses it would have missed
    the password too.
    """
    holders = _processes_holding(running_wallet, CANARY_VAR)
    assert holders, "the probe found a planted variable nowhere — it measures nothing"
