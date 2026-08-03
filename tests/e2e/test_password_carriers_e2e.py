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

# `podman run --init` inserts its own PID 1 into the container. It receives the
# runtime's environment before our entrypoint exists, so nothing inside the image
# can clear it — under `-e` delivery it is an unreachable carrier by construction.
# Named here so the `-e` case can exclude it explicitly instead of loosening the
# assertion; under `_FILE` delivery it must come up clean like everything else.
FOREIGN_INIT = ("podman-init", "catatonit", "tini")


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
    """Criterion 1(c): the `-e` path — nothing of OURS carries it.

    The container config still holds the value (`podman inspect`), and under
    `--init` the runtime's PID 1 would too; neither is reachable from inside the
    image, and both are documented. What must be clean is every process the image
    itself starts — including PID 1, which is our entrypoint until it `exec`s.
    """
    carriers = password_carriers(env_delivered_wallet)
    ours = [c for c in carriers if c["comm"] not in FOREIGN_INIT]
    assert ours == [], (
        f"the keyring password is readable in /proc/<pid>/environ of: {[c['comm'] for c in ours]}"
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
