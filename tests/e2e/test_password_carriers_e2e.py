"""Acceptance: no process inside the wallet carries the keyring password.

`/proc/<pid>/environ` is the cheapest way there is to harvest a secret from a
running box, and until this circle every process of the wallet image held the
keyring password there — even under the `_FILE` delivery, because the entrypoint
read the file and `export`ed the value straight back out to its children.

What is asserted here is the property, not the mechanism: whatever the entrypoint
does internally, once the wallet is serving, a reader of `/proc` must come up
empty. Measured against the shipped image, so a regression in a future entrypoint
fails here rather than in a customer's container.

Redaction discipline: assertions carry process names and counts, never container
output — `create_wallet`'s stderr holds the recovery phrase.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.conftest import Chain
from tests.e2e.podman import podman, rm_force, volume_rm
from tests.e2e.wallet import KEYRING_PASSWORD, create_wallet, start_wallet

pytestmark = pytest.mark.e2e

# Read every process's environment from inside the container and report which
# ones hold the password. Runs as the container user, which owns every process
# in there, so `environ` is readable for all of them.
#
# The probe excludes ITSELF and nothing else: `podman exec` hands the new process
# the container's *configured* environment, so under `-e` delivery the probe is
# born holding the password no matter how clean the running processes are. That
# is a property of exec, not of the wallet — counting it would make the test
# unpassable and prove nothing.
_CARRIER_PROBE = r"""
import json, os, sys

password = sys.argv[1].encode()
self_pid = os.getpid()
carriers = []
for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    pid = int(entry)
    if pid == self_pid:
        continue
    try:
        with open("/proc/%d/environ" % pid, "rb") as handle:
            environ = handle.read()
        with open("/proc/%d/comm" % pid, "rb") as handle:
            comm = handle.read().decode("utf-8", "replace").strip()
    except OSError:
        continue
    if password in environ:
        carriers.append({"pid": pid, "comm": comm})
print(json.dumps(carriers))
"""

# Nothing is excluded by process name. `podman run --init` would insert a PID 1
# the image cannot reach, and under `-e` delivery that one would be a carrier by
# construction — but no test here combines the two, and excluding by name would
# also exempt OUR own PID 1, which is called `tini` after the entrypoint hands
# the role over. That process is exactly the one the fix has to clean, so a name
# filter would hide the regression it exists to catch.


def password_carriers(container: str, password: str = KEYRING_PASSWORD) -> list[dict[str, object]]:
    """Which processes in `container` hold `password` in their environment."""
    done = podman("exec", "-i", container, "python3", "-c", _CARRIER_PROBE, password)
    carriers: list[dict[str, object]] = json.loads(done.stdout)
    return carriers


@pytest.fixture
def secret_name(tmp_path: Path) -> Iterator[str]:
    """A podman secret holding the keyring password; removed after the test."""
    name = f"rustok-e2e-carrier-{uuid.uuid4().hex[:8]}"
    source = tmp_path / "keyring-password"
    source.write_text(KEYRING_PASSWORD, encoding="utf-8")
    source.chmod(0o600)
    podman("secret", "create", name, str(source))
    try:
        yield name
    finally:
        podman("secret", "rm", name, check=False)


def _run_wallet(
    chain: Chain,
    image: str,
    tmp_path: Path,
    tag: str,
    password_args: tuple[str, ...],
    extra_args: tuple[str, ...] = (),
) -> Iterator[str]:
    """Onboard and start one wallet; yield its container name."""
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-tui-e2e-{tag}-{suffix}"
    volume = f"rustok-e2e-data-{tag}-{suffix}"

    podman("volume", "create", volume)
    try:
        create_wallet(image, chain.network, volume, password_args=password_args)
        mcp = start_wallet(
            image=image,
            network=chain.network,
            volume=volume,
            name=name,
            anvil_url=chain.url_from_container,
            stderr_path=tmp_path / f"{name}.stderr.log",
            password_args=password_args,
            extra_args=extra_args,
        )
        try:
            yield name
        finally:
            mcp.close()
    finally:
        rm_force(name)
        volume_rm(volume)


@pytest.fixture
def file_delivered_wallet(
    chain: Chain, image: str, tmp_path: Path, secret_name: str
) -> Iterator[str]:
    """The documented run: the password arrives as a mounted secret, no `--init`."""
    yield from _run_wallet(
        chain,
        image,
        tmp_path,
        tag="carrier-file",
        password_args=(
            "--secret",
            f"{secret_name},type=mount,mode=0400,uid=1000,gid=1000",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/{secret_name}",
        ),
    )


@pytest.fixture
def file_delivered_wallet_with_init(
    chain: Chain, image: str, tmp_path: Path, secret_name: str
) -> Iterator[str]:
    """The same delivery under `--init`, which adds a PID 1 we do not control."""
    yield from _run_wallet(
        chain,
        image,
        tmp_path,
        tag="carrier-init",
        password_args=(
            "--secret",
            f"{secret_name},type=mount,mode=0400,uid=1000,gid=1000",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/{secret_name}",
        ),
        extra_args=("--init",),
    )


@pytest.fixture
def env_delivered_wallet(chain: Chain, image: str, tmp_path: Path) -> Iterator[str]:
    """The compatibility run: the password still arrives as a plain `-e` value."""
    yield from _run_wallet(
        chain,
        image,
        tmp_path,
        tag="carrier-env",
        password_args=("-e", f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}"),
    )


def test_file_delivery_leaves_the_password_in_no_process_environment(
    file_delivered_wallet: str,
) -> None:
    """Criterion 1(a): the documented run — zero carriers, no exceptions.

    Red against v0.8.2: the entrypoint reads the secret file and `export`s the
    value, so core, gateway and the MCP server all carry it.
    """
    carriers = password_carriers(file_delivered_wallet)
    assert carriers == [], (
        "the keyring password is readable in /proc/<pid>/environ of: "
        f"{[c['comm'] for c in carriers]}"
    )


def test_file_delivery_stays_clean_under_init(
    file_delivered_wallet_with_init: str,
) -> None:
    """Criterion 1(b): `--init` adds a PID 1 we do not control — still zero.

    Under file delivery the runtime's own environment holds a path, so even the
    process the image cannot reach has nothing worth reading.
    """
    carriers = password_carriers(file_delivered_wallet_with_init)
    assert carriers == [], (
        "the keyring password is readable in /proc/<pid>/environ of: "
        f"{[c['comm'] for c in carriers]}"
    )


def test_env_delivery_leaves_the_password_in_no_process_of_our_chain(
    env_delivered_wallet: str,
) -> None:
    """Criterion 1(c): the `-e` path — no process in the container carries it.

    No exemptions, PID 1 included: it is our own entrypoint, and the `exec` that
    hands its role to tini is precisely what rewrites the environment region the
    `unset` could not reach. Excusing it by name would excuse the mechanism under
    test.

    What stays outside this assertion is outside the *container*: the runtime
    keeps the value in the container config (`podman inspect`), and under
    `--init` in its own PID 1. Neither is reachable from inside the image, both
    are documented, and neither is a process this test can see.
    """
    carriers = password_carriers(env_delivered_wallet)
    assert carriers == [], (
        "the keyring password is readable in /proc/<pid>/environ of: "
        f"{[c['comm'] for c in carriers]}"
    )


def test_the_temporary_password_file_does_not_outlive_startup(
    env_delivered_wallet: str,
) -> None:
    """A password handed over by `-e` is staged on disk, then removed.

    The staging file is how the core gets a password that no longer travels in
    anyone's environment. Once the wallet serves, it has done its job: leaving it
    behind would trade an environment carrier for a disk one.
    """
    listing = podman(
        "exec", "-i", env_delivered_wallet, "sh", "-c", "ls -a /run/wallet"
    ).stdout.split()
    leftovers = [entry for entry in listing if "password" in entry or "keyring" in entry]
    assert leftovers == [], f"a staged password file outlived startup: {leftovers}"


@pytest.mark.e2e_slow
def test_a_start_that_never_comes_up_leaves_no_staged_password(image: str) -> None:
    """A failed start must not leave the password in the container's filesystem.

    The container is deliberately started WITHOUT `--rm` on an empty volume, so
    the core exits, the entrypoint gives up at its own timeout, and the stopped
    container stays — which is exactly what someone debugging a failed start
    does. `podman diff` then reads its writable layer from the host: a staged
    password left there is recoverable with `podman cp` by anyone who can talk
    to the engine, a wider audience than the same-user access the threat model
    accepts.

    Marked slow: it waits out the entrypoint's 60-second core-ready timeout.
    (Red-proven by measurement: before the cleanup covered every exit path, the
    file was in the exited container's layer.)
    """
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-tui-e2e-failed-{suffix}"
    volume = f"rustok-e2e-data-failed-{suffix}"

    podman("volume", "create", volume)
    try:
        # No wallet in the volume: the core refuses to start, and the entrypoint
        # times out waiting for it.
        podman(
            "run",
            "-d",
            "-i",
            "--name",
            name,
            "-v",
            f"{volume}:/data",
            "-e",
            f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
            image,
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = podman("inspect", "-f", "{{.State.Status}}", name).stdout.strip()
            if state == "exited":
                break
            time.sleep(2)
        else:
            raise AssertionError("the container never exited; the timeout path was not exercised")

        # `podman diff` lists what the container wrote into its own layer.
        changes = podman("diff", name).stdout
        staged = [line for line in changes.splitlines() if "keyring-password" in line]
        assert staged == [], f"a failed start left the password on disk: {staged}"
    finally:
        rm_force(name)
        volume_rm(volume)


def test_a_password_file_the_wallet_can_write_to_is_still_never_deleted(
    chain: Chain, image: str, tmp_path: Path
) -> None:
    """The cleanup must touch only what the entrypoint itself wrote.

    The password file lives in the wallet's own data volume — the one delivery
    where the container genuinely *can* unlink it, and a realistic one: an
    operator who already mounts a volume for the keystore may well keep the
    password beside it. Both other deliveries are protected by the runtime
    rather than by us (a podman secret mount is read-only; a `:z` bind-mount is
    not writable by the container user), so a test riding those would be proving
    podman's behaviour instead of ours.

    (Red-proven by mutation: an entrypoint that removes `$PASSWORD_FILE` rather
    than only its own staged copy fails this test — see the PR report.)
    """
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-tui-e2e-carrier-vol-{suffix}"
    volume = f"rustok-e2e-data-carrier-vol-{suffix}"
    password_args = ("-e", "RUSTOK_KEYRING_PASSWORD_FILE=/data/keyring-pass")

    podman("volume", "create", volume)
    try:
        # Seed the password into the volume as the container user, so the wallet
        # is able to delete it — that is the whole point of this delivery.
        podman(
            "run",
            "--rm",
            "-v",
            f"{volume}:/data",
            "--entrypoint",
            "sh",
            image,
            "-c",
            f"printf %s '{KEYRING_PASSWORD}' >/data/keyring-pass && chmod 600 /data/keyring-pass",
        )
        create_wallet(image, chain.network, volume, password_args=password_args)
        mcp = start_wallet(
            image=image,
            network=chain.network,
            volume=volume,
            name=name,
            anvil_url=chain.url_from_container,
            stderr_path=tmp_path / f"{name}.stderr.log",
            password_args=password_args,
        )
        try:
            inside = podman("exec", "-i", name, "sh", "-c", "cat /data/keyring-pass", check=False)
            assert inside.returncode == 0, "the operator's password file must still be there"
            assert inside.stdout.strip() == KEYRING_PASSWORD, "it must be unchanged"
        finally:
            mcp.close()
    finally:
        rm_force(name)
        volume_rm(volume)
