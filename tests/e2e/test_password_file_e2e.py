"""Acceptance: the keyring password delivered as a FILE (`RUSTOK_KEYRING_PASSWORD_FILE`).

Ported from the console line's PR-1.1 suite (`e0b7a1f`) and trimmed to the agent
edition — no approval console, no PIN, no local chain. The entrypoint accepts the
password via the standard `_FILE` convention — no plaintext in `inspect`, MCP
configs or shell history. Live coverage here is podman (secret type=mount, and a
bind-mounted plain file). The docker fallback rides the same engine-agnostic
mechanism (an env var plus a mounted file), but docker itself is NOT exercised by
this suite — its 0600/uid-matched specifics are manually probed only.

Redaction discipline: `create_wallet` output carries the recovery phrase — no raw
container output may ever reach a failure message here (same contract as
`wallet.create_wallet`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.podman import podman, rm_force, volume_rm
from tests.e2e.wallet import KEYRING_PASSWORD, Wallet, create_wallet, start_wallet

pytestmark = pytest.mark.e2e

# Quotes and `$` must survive the _FILE path byte-exact (the console line proved
# the same password through a podman secret against its own image).
QUOTED_PASSWORD = "pa\"ss$wo'rd"  # noqa: S105  (throwaway keystore, per-test volume)

# The entrypoint's named errors — asserted as substrings: a silent 60s "core not
# ready" timeout instead of these is exactly the failure mode this circle removes.
NOT_A_FILE_ERROR = "RUSTOK_KEYRING_PASSWORD_FILE does not point to a readable regular file"
EMPTY_ERROR = "RUSTOK_KEYRING_PASSWORD_FILE is empty"


@pytest.fixture
def password_secret(tmp_path: Path) -> Iterator[str]:
    """A podman secret holding the quoted password; removed after the test.

    Created from a file, not stdin — the `podman` helper is a fixed no-input argv.
    The file is a 0600 throwaway inside pytest's private tmp dir. The name is
    uuid-random: a deterministic name survives a killed run and collides with the
    next one.
    """
    name = f"rustok-e2e-pass-{uuid.uuid4().hex[:8]}"
    source = tmp_path / "keyring-password"
    source.write_text(QUOTED_PASSWORD, encoding="utf-8")
    source.chmod(0o600)
    podman("secret", "create", name, str(source))
    try:
        yield name
    finally:
        podman("secret", "rm", name, check=False)


@pytest.fixture
def file_wallet(image: str, tmp_path: Path, password_secret: str) -> Iterator[Wallet]:
    """A wallet onboarded AND started with the password arriving only as a file.

    The password rides `--secret …,type=mount` + `RUSTOK_KEYRING_PASSWORD_FILE` —
    never `-e` with a value, never argv.
    """
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-e2e-file-{suffix}"
    volume = f"rustok-e2e-data-file-{suffix}"
    password_args = (
        "--secret",
        f"{password_secret},type=mount",
        "-e",
        f"RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/{password_secret}",
    )

    podman("volume", "create", volume)
    try:
        address = create_wallet(image, volume, password_args=password_args)
        mcp = start_wallet(
            image=image,
            volume=volume,
            name=name,
            stderr_path=tmp_path / f"{name}.stderr.log",
            password_args=password_args,
        )
        try:
            yield Wallet(name=name, address=address, mcp=mcp)
        finally:
            mcp.close()
    finally:
        rm_force(name)
        volume_rm(volume)


def test_env_secret_password_unlock_and_no_plaintext_in_inspect(
    image: str, tmp_path: Path, password_secret: str
) -> None:
    """The documented podman path: `--secret …,type=env,target=RUSTOK_KEYRING_PASSWORD`.

    The console line verified byte-exact injection with quotes and absence from
    `podman inspect` by manual probe; this test locks both on the agent line.
    The `_FILE` env var is NOT involved here — the secret becomes the password
    env var directly, and inspect must still never show the value.
    """
    suffix = uuid.uuid4().hex[:8]
    name = f"rustok-wallet-e2e-env-{suffix}"
    volume = f"rustok-e2e-data-env-{suffix}"
    password_args = (
        "--secret",
        f"{password_secret},type=env,target=RUSTOK_KEYRING_PASSWORD",
    )

    podman("volume", "create", volume)
    try:
        address = create_wallet(image, volume, password_args=password_args)
        mcp = start_wallet(
            image=image,
            volume=volume,
            name=name,
            stderr_path=tmp_path / f"{name}.stderr.log",
            password_args=password_args,
        )
        try:
            inspected = podman("inspect", name).stdout
            assert password_secret in inspected, (
                "inspect output does not even show the secret itself — wrong container?"
            )
            for form, label in (
                (QUOTED_PASSWORD, "raw"),
                (json.dumps(QUOTED_PASSWORD).strip('"'), "json-escaped"),
            ):
                assert form not in inspected, (
                    f"the keyring password leaked into `podman inspect` ({label} form)"
                )
            config_env: list[str] = json.loads(inspected)[0]["Config"]["Env"]
            leaked = [line for line in config_env if line.startswith("RUSTOK_KEYRING_PASSWORD=")]
            assert not leaked, (
                "a type=env secret must not surface in Config.Env — that is the whole point"
            )
            context = mcp.tool("get_wallet_context", {})
            assert context.get("address") == address, (
                "the wallet must serve the keystore it onboarded with a secret-env password"
            )
        finally:
            mcp.close()
    finally:
        rm_force(name)
        volume_rm(volume)


def test_file_password_unlock_and_no_plaintext_in_inspect(file_wallet: Wallet) -> None:
    """The wallet is fully operational on a file-delivered password with quotes.

    Onboarding unlocked the keystore (the fixture), and the running wallet answers
    `get_wallet_context` with the same address — byte-exact fidelity of a password
    containing `"`, `$` and `'`. While it runs, `podman inspect` must carry the
    file PATH, never the password value.
    """
    # Strict no-plaintext assert, with a positive control against vacuity: the
    # inspect output must be real enough to show the _FILE variable itself.
    inspected = podman("inspect", file_wallet.name).stdout
    assert "RUSTOK_KEYRING_PASSWORD_FILE=/run/secrets/" in inspected, (
        "inspect output does not even show the _FILE env var — wrong container?"
    )
    for form, label in (
        (QUOTED_PASSWORD, "raw"),
        (json.dumps(QUOTED_PASSWORD).strip('"'), "json-escaped"),
    ):
        assert form not in inspected, (
            f"the keyring password leaked into `podman inspect` ({label} form)"
        )
    config_env: list[str] = json.loads(inspected)[0]["Config"]["Env"]
    leaked = [line for line in config_env if line.startswith("RUSTOK_KEYRING_PASSWORD=")]
    assert not leaked, "Config.Env must never carry RUSTOK_KEYRING_PASSWORD with a value"

    context = file_wallet.mcp.tool("get_wallet_context", {})
    assert context.get("address") == file_wallet.address, (
        "the wallet must serve the keystore it onboarded with a file-delivered password"
    )


def test_missing_password_file_fails_fast_with_named_error(image: str) -> None:
    """`_FILE` pointing nowhere must die at the entrypoint with a named error.

    Not a 60-second "core not ready" hang, not a cryptic core failure — the named
    error is what a human debugging a broken secret mount actually needs.
    """
    done = podman(
        "run",
        "--rm",
        "-e",
        "RUSTOK_KEYRING_PASSWORD_FILE=/nonexistent/keyring-pass",
        image,
        "create-wallet",
        check=False,
        timeout=60,
    )
    # Booleans only past this point: `create-wallet` output is where the recovery
    # phrase lives, and pytest's assert introspection pastes referenced values into
    # the report — the raw output must never be one of them.
    failed = done.returncode != 0
    named = NOT_A_FILE_ERROR in done.stderr
    assert failed, "a missing password file must fail the container"
    assert named, (
        "the entrypoint must name the unusable RUSTOK_KEYRING_PASSWORD_FILE "
        f"(exit {done.returncode}; stderr redacted: {len(done.stderr)} chars)"
    )


def test_empty_password_file_fails_with_named_error(image: str, tmp_path: Path) -> None:
    """An empty password file must be refused by name, not passed on as ''.

    Delivered as a bind-mounted plain file. This is the same MECHANISM the docker
    fallback uses (mounted file + `_FILE` env var), but the run below is still
    podman: `:z`/0644 are podman/SELinux-specifics (rootless podman hands the file
    to the container root-owned, so 0600 would be unreadable here). Docker's own
    0600/uid-matched behaviour is manually probed only — NOT covered by this suite.
    An unreadable mount is a DIFFERENT named error, guarded by
    `test_missing_password_file…`.
    """
    empty = tmp_path / "empty-password"
    empty.write_text("", encoding="utf-8")
    empty.chmod(0o644)
    done = podman(
        "run",
        "--rm",
        "-v",
        f"{empty}:/run/keyring-pass:ro,z",
        "-e",
        "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
        image,
        "create-wallet",
        check=False,
        timeout=60,
    )
    # Same redaction rule as above: assert booleans, never the raw stderr.
    failed = done.returncode != 0
    named = EMPTY_ERROR in done.stderr
    assert failed, "an empty password file must fail the container"
    assert named, (
        "the entrypoint must name the empty RUSTOK_KEYRING_PASSWORD_FILE "
        f"(exit {done.returncode}; stderr redacted: {len(done.stderr)} chars)"
    )


def test_explicit_env_password_wins_over_file(image: str) -> None:
    """The `_FILE` convention: an explicit env var wins, the file is not even read.

    Onboarding succeeds with a valid `-e` password even though `_FILE` points
    nowhere — proving both the precedence and that the unreadable-file check does
    not fire when the password already arrived. (Red-proven by mutation on the
    console line: an entrypoint that reads the file first fails this test.)
    """
    volume = f"rustok-e2e-data-prec-{uuid.uuid4().hex[:8]}"
    podman("volume", "create", volume)
    try:
        address = create_wallet(
            image,
            volume,
            password_args=(
                "-e",
                f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
                "-e",
                "RUSTOK_KEYRING_PASSWORD_FILE=/nonexistent/keyring-pass",
            ),
        )
        assert address.startswith("0x")
    finally:
        volume_rm(volume)


def test_device_password_file_fails_with_named_error(image: str) -> None:
    """`_FILE` at a non-regular file (a device, a FIFO, a dir) must die by name.

    `cat` on such a path can block forever — WORSE than the 60s hang this circle
    removes. `/dev/null` stands in for the class: it exists in every container,
    needs no mount, and is not a regular file.
    """
    done = podman(
        "run",
        "--rm",
        "-e",
        "RUSTOK_KEYRING_PASSWORD_FILE=/dev/null",
        image,
        "create-wallet",
        check=False,
        timeout=60,
    )
    # Same redaction rule as above: assert booleans, never the raw stderr.
    failed = done.returncode != 0
    named = NOT_A_FILE_ERROR in done.stderr
    assert failed, "a non-regular password file must fail the container"
    assert named, (
        "the entrypoint must name the non-regular RUSTOK_KEYRING_PASSWORD_FILE "
        f"(exit {done.returncode}; stderr redacted: {len(done.stderr)} chars)"
    )


def test_trailing_newline_in_password_file_is_stripped(image: str, tmp_path: Path) -> None:
    """The documented `_FILE` contract: `$(cat …)` strips trailing newlines.

    Locked across the delivery boundary: the wallet is CREATED with the plain
    `-e` password and STARTED with a file holding the same password plus `\\n`
    (what `echo`-made files carry). The keystore unlocks — the MCP handshake in
    `start_wallet` fails otherwise — only if the file path stripped the newline
    to the byte-identical password.
    """
    suffix = uuid.uuid4().hex[:8]
    volume = f"rustok-e2e-data-nl-{suffix}"
    name = f"rustok-wallet-e2e-nl-{suffix}"
    password_file = tmp_path / "password-with-newline"
    password_file.write_text(KEYRING_PASSWORD + "\n", encoding="utf-8")
    password_file.chmod(0o644)

    podman("volume", "create", volume)
    try:
        create_wallet(image, volume)  # plain -e delivery
        mcp = start_wallet(
            image=image,
            volume=volume,
            name=name,
            stderr_path=tmp_path / f"{name}.stderr.log",
            password_args=(
                "-v",
                f"{password_file}:/run/keyring-pass:ro,z",
                "-e",
                "RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass",
            ),
        )
        # The handshake inside start_wallet IS the assertion (a wrong password
        # never unlocks the keystore); one tool call proves the channel end2end.
        try:
            context = mcp.tool("get_wallet_context", {})
        finally:
            mcp.close()
        assert context, "the wallet must answer over MCP after a file unlock"
    finally:
        rm_force(name)
        volume_rm(volume)
