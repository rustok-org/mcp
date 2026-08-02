"""The agent-line wallet under test: one container, one fresh keystore.

Trimmed for the agent edition: no approval console, no PIN, no local chain —
the unlock proof is onboarding + a running MCP channel answering
`get_wallet_context` (a wrong password never lets core serve the keystore).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.e2e.mcp_client import McpStdio
from tests.e2e.podman import PODMAN

KEYRING_PASSWORD = "e2e-keyring-password"  # noqa: S105  (throwaway keystore, per-test volume)

_ADDRESS_RE = re.compile(r"Address:\s+(0x[0-9a-fA-F]{40})")

# The recovery phrase is printed on its own indented line, between the banner
# header and the warning that follows it. Matching the words themselves — not the
# "(N words)" the header claims — is the point: the header is a string, the phrase
# is the behaviour.
_PHRASE_RE = re.compile(r"^ +([a-z]+(?: [a-z]+)+)\s*$", re.MULTILINE)


@dataclass
class Wallet:
    """A running wallet container plus the address its human was shown once."""

    name: str
    address: str
    mcp: McpStdio


def create_wallet(
    image: str,
    volume: str,
    password_args: tuple[str, ...] | None = None,
) -> str:
    """Run one-shot onboarding and return the address shown to the human once.

    `password_args` is the podman-run fragment that delivers the keyring password
    (default: the plain `-e` env var). The `_FILE` acceptance passes a
    `--secret`/`RUSTOK_KEYRING_PASSWORD_FILE` fragment instead — the password value
    itself must never ride the argv.

    NOTHING from this command's output may ever reach a failure message. The output
    is where the wallet prints the recovery phrase — the secret the whole
    product exists to protect — and this suite's log is pasted whole into the
    acceptance report. So this is the one call site that must NOT use the shared
    helper's "echo stderr so a human can debug it" behaviour: a container that dies
    AFTER printing the banner would publish a real, spendable seed phrase.
    """
    if password_args is None:
        password_args = ("-e", f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}")

    timed_out_after: float | None = None
    done: subprocess.CompletedProcess[str] | None = None
    try:
        done = subprocess.run(
            [
                PODMAN,
                "run",
                "--rm",
                "-i",
                "-v",
                f"{volume}:/data",
                *password_args,
                image,
                "create-wallet",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as timed_out:
        # `TimeoutExpired` carries the captured output as attributes: a container that
        # printed the banner and then hung hands the recovery phrase to anything that
        # walks this exception. Keep the number, drop the object.
        timed_out_after = timed_out.timeout

    if timed_out_after is not None:
        raise AssertionError(
            f"create-wallet timed out after {timed_out_after}s "
            "(output redacted — it contains the recovery phrase)"
        )
    assert done is not None

    # The agent line prints the banner to stdout; look in both, echo neither.
    output = done.stdout + done.stderr
    address = _ADDRESS_RE.search(output)
    if done.returncode != 0 or not address:
        raise AssertionError(
            f"create-wallet failed or printed an unexpected format (exit {done.returncode}; "
            f"output redacted — it contains the recovery phrase; {len(output)} chars, "
            f"address matched: {bool(address)})"
        )
    return address.group(1)


def create_wallet_phrase_word_count(
    image: str,
    volume: str,
    password_args: tuple[str, ...] | None = None,
) -> int:
    """Run one-shot onboarding and return ONLY how many words the phrase has.

    Same redaction contract as `create_wallet`, and the same reason: a count
    cannot spend anything, a phrase can. The phrase never leaves this function —
    not into a return value, not into an assertion message, not into a log.

    Counting the words themselves rather than reading the "(N words)" the banner
    claims is deliberate: the header is a string a careless edit could desync from
    reality, and this test exists precisely to catch that.
    """
    if password_args is None:
        password_args = ("-e", f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}")

    try:
        done = subprocess.run(
            [
                PODMAN,
                "run",
                "--rm",
                "-i",
                "-v",
                f"{volume}:/data",
                *password_args,
                image,
                "create-wallet",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as timed_out:
        # Never let the exception object escape: it carries the captured banner.
        raise AssertionError(
            f"create-wallet timed out after {timed_out.timeout}s "
            "(output redacted — it contains the recovery phrase)"
        ) from None

    output = done.stdout + done.stderr
    phrase = _PHRASE_RE.search(output)
    if done.returncode != 0 or not phrase:
        raise AssertionError(
            f"create-wallet failed or printed an unexpected format (exit {done.returncode}; "
            f"output redacted — it contains the recovery phrase; {len(output)} chars, "
            f"phrase line matched: {bool(phrase)})"
        )
    return len(phrase.group(1).split())


def start_wallet(
    image: str,
    volume: str,
    name: str,
    stderr_path: Path,
    password_args: tuple[str, ...] | None = None,
) -> McpStdio:
    """Start the wallet container with its stdio as the MCP channel.

    No RPC URLs are configured: the enabled chains are simply skipped, and
    `get_wallet_context` still answers — which is exactly the unlock proof this
    suite needs (core cannot serve the keystore with a wrong password).

    `password_args` — same contract as in `create_wallet`.
    """
    if password_args is None:
        password_args = ("-e", f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}")

    argv = [
        PODMAN,
        "run",
        "--rm",
        "-i",
        "--init",
        "--name",
        name,
        "-v",
        f"{volume}:/data",
        *password_args,
        image,
    ]
    mcp = McpStdio(argv, stderr_path)
    try:
        # The handshake is where a broken container surfaces (it waits for core +
        # gateway). If it fails, the caller never gets the object — so the subprocess,
        # its pipes and the stderr handle have to be released right here.
        mcp.initialize()
    except BaseException:
        mcp.close()
        raise
    return mcp
