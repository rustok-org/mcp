"""The wallet under test: one container, one fresh keystore, one PIN.

Each scenario gets its own wallet. That is not tidiness — the PIN lockout ladder
lives on disk in the data dir (core `pin.rs`) and lasts five minutes, so a shared
keystore would let the lockout scenario fail its neighbours with `locked`.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.e2e.mcp_client import McpStdio
from tests.e2e.podman import PODMAN, podman

KEYRING_PASSWORD = "e2e-keyring-password"  # noqa: S105  (throwaway keystore, per-test volume)
CHAIN_ID = 31337
SOCKET_PATH = "/run/wallet/approve.sock"

_ADDRESS_RE = re.compile(r"Address:\s+(0x[0-9a-fA-F]{40})")
# Anchored to its own label: an unanchored "any indented 6 digits" would silently pick
# up some other number if the banner ever changes, and the suite would then fail with
# "Wrong PIN" — sending the next debugger down the wrong road.
_PIN_RE = re.compile(r"Transaction-approval PIN[^\n]*\n\s*\n\s*(\d{6})\s*$", re.MULTILINE)

# Raw approver-socket client, executed INSIDE the container: the socket is not
# mounted out, so the host cannot reach it. The image ships python3 (its runtime is
# python:3.12-slim), so no extra tooling is needed. Speaks the JSON-Lines protocol
# of `console/docs/APPROVER-PROTOCOL.md` and prints every response as JSON.
_SOCKET_CLIENT = f"""
import json, socket, sys

ops = json.loads(sys.argv[1])
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(20)
sock.connect({SOCKET_PATH!r})
channel = sock.makefile("rw")
answers = []
for op in ops:
    channel.write(json.dumps(op) + "\\n")
    channel.flush()
    answers.append(json.loads(channel.readline()))
print(json.dumps(answers))
"""


def unlimited_approve_calldata(spender: str) -> str:
    """ERC-20 `approve(spender, 2**256-1)` — the drain vector the card must shout about."""
    padded_spender = spender.lower().removeprefix("0x").rjust(64, "0")
    return "0x095ea7b3" + padded_spender + "f" * 64


@dataclass
class Wallet:
    """A running wallet container plus the two secrets its human was shown."""

    name: str
    address: str
    pin: str
    mcp: McpStdio

    def exec(self, *command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a command inside the wallet container."""
        return podman("exec", "-i", self.name, *command, check=check)

    def socket_ops(self, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Speak the approver protocol directly, bypassing the console TUI.

        The console cannot send some requests at all (it gates them client-side), so
        the server's own answers — `unauthorized`, `pin_required` — are only reachable
        from a raw client.
        """
        done = self.exec("python3", "-c", _SOCKET_CLIENT, json.dumps(ops), check=False)
        if done.returncode != 0 or not done.stdout.strip():
            # These are the two security gates (unauthorized / pin_required): a broken
            # client here must say WHY, not die on an empty JSON parse.
            raise AssertionError(
                f"the approver-socket client failed (exit {done.returncode}): "
                f"{done.stderr.strip() or '(no stderr)'}"
            )
        answers: list[dict[str, Any]] = json.loads(done.stdout)
        return answers

    def park_send(self, to: str, wei: int) -> str:
        """Agent-side: preview a native send, then execute it — which parks it."""
        preview = self.mcp.tool(
            "preview_transaction",
            {"to": to, "value": str(wei), "chain_id": CHAIN_ID},
        )
        parked = self.mcp.tool("execute_transaction", {"preview_id": preview["preview_id"]})
        assert parked["state"] == "pending", f"expected a parked tx, got {parked}"
        preview_id: str = preview["preview_id"]
        return preview_id

    def park_unlimited_approve(self, token: str, spender: str) -> str:
        """Agent-side: park an unlimited ERC-20 approval (high-risk by construction)."""
        preview = self.mcp.tool(
            "preview_transaction",
            {
                "to": token,
                "value": "0",
                "chain_id": CHAIN_ID,
                "data": unlimited_approve_calldata(spender),
            },
        )
        parked = self.mcp.tool("execute_transaction", {"preview_id": preview["preview_id"]})
        assert parked["state"] == "pending", f"expected a parked tx, got {parked}"
        preview_id: str = preview["preview_id"]
        return preview_id

    def status(self, preview_id: str) -> dict[str, Any]:
        """Agent-side polling: what became of the parked transaction."""
        return self.mcp.tool("get_execution_status", {"preview_id": preview_id})


def create_wallet(image: str, network: str, volume: str) -> tuple[str, str]:
    """Run one-shot onboarding and return the (address, PIN) shown to the human once.

    NOTHING from this command's output may ever reach a failure message. Its stderr is
    where the wallet prints the 12-word recovery phrase and the approval PIN — the two
    secrets the whole product exists to protect — and this suite's log is pasted whole
    into the acceptance report. So this is the one call site that must NOT use the
    shared helper's "echo stderr so a human can debug it" behaviour: a container that
    dies AFTER printing the banner would publish a real, spendable seed phrase.
    """
    done = podman(
        "run",
        "--rm",
        "-i",
        "--network",
        network,
        "-v",
        f"{volume}:/data",
        "-e",
        f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
        image,
        "create-wallet",
        timeout=120,
        check=False,  # a non-zero exit must NOT raise with the raw stderr attached
    )
    output = done.stderr
    address = _ADDRESS_RE.search(output)
    pin = _PIN_RE.search(output)
    if done.returncode != 0 or not address or not pin:
        raise AssertionError(
            f"create-wallet failed or printed an unexpected format (exit {done.returncode}; "
            f"output redacted — it contains the recovery phrase; {len(output)} chars, "
            f"address matched: {bool(address)}, PIN matched: {bool(pin)})"
        )
    return address.group(1), pin.group(1)


def start_wallet(
    image: str,
    network: str,
    volume: str,
    name: str,
    anvil_url: str,
    stderr_path: Path,
) -> McpStdio:
    """Start the wallet container with its stdio as the MCP channel."""
    argv = [
        PODMAN,
        "run",
        "--rm",
        "-i",
        "--init",
        "--name",
        name,
        "--network",
        network,
        "-v",
        f"{volume}:/data",
        "-e",
        f"RUSTOK_KEYRING_PASSWORD={KEYRING_PASSWORD}",
        "-e",
        f"RUSTOK_ALLOWED_CHAINS={CHAIN_ID}",
        "-e",
        f"RUSTOK_RPC_URLS_{CHAIN_ID}={anvil_url}",
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
