"""Candidate acceptance against real MCP, HTTP, core and an isolated local chain."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import Chain
from tests.e2e.podman import podman
from tests.e2e.test_approval_e2e import RECIPIENT, SEND_WEI, wait_status
from tests.e2e.wallet import CHAIN_ID, Wallet, start_wallet

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def engine_command() -> str:
    """Keep the rootless engine store while isolating shim HOME/config."""
    real = shutil.which("podman")
    assert real
    actual_home = os.environ["HOME"]
    args = [
        "env",
        f"HOME={actual_home}",
        "XDG_CONFIG_HOME=" + os.environ.get("XDG_CONFIG_HOME", actual_home + "/.config"),
        "XDG_DATA_HOME=" + os.environ.get("XDG_DATA_HOME", actual_home + "/.local/share"),
        real,
    ]
    return shlex.join(args)


def human(wallet: Wallet, *ops: dict[str, Any]) -> list[dict[str, Any]]:
    answers = wallet.socket_ops(
        [{"op": "hello", "proto": 4}, {"op": "auth", "pin": wallet.pin}, *ops]
    )
    assert answers[0]["ok"] and answers[1]["ok"]
    return answers[2:]


def mode(wallet: Wallet, value: str) -> None:
    result = human(wallet, {"op": "set_mode", "mode": value, "pin": wallet.pin})[0]
    assert result == {"ok": True, "mode": value, "origin": "acknowledged"}


def observed(chain: Chain, wallet: Wallet) -> tuple[int, str]:
    return chain.anvil.balance(RECIPIENT), chain.anvil.rpc(
        "eth_getTransactionCount", [wallet.address, "pending"]
    )


def http(wallet: Wallet, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
    # The gateway is loopback-only inside the wallet. Its fixture key stays
    # inside the container; only the status and response body leave this probe.
    code = """
import json, pathlib, sys, urllib.request, urllib.error
key = pathlib.Path('/run/wallet/gateway-key').read_text().strip()
body = json.loads(sys.argv[2])
req = urllib.request.Request('http://127.0.0.1:3000' + sys.argv[1],
    data=None if body is None else json.dumps(body).encode(),
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
try:
    response = urllib.request.urlopen(req, timeout=20)
except urllib.error.HTTPError as error:
    response = error
print(json.dumps({'status': response.code, 'body': json.loads(response.read())}))
"""
    return json.loads(wallet.exec("python3", "-c", code, path, json.dumps(body)).stdout)


def test_autonomy_is_confirmed_and_replay_does_not_broadcast_twice(
    wallet: Wallet, chain: Chain
) -> None:
    mode(wallet, "autonomous")
    before = observed(chain, wallet)
    with pytest.raises(RuntimeError, match="expired or unknown"):
        wallet.mcp.tool("execute_transaction", {"preview_id": str(uuid.uuid4())})
    assert observed(chain, wallet) == before
    preview = wallet.mcp.tool(
        "preview_transaction", {"to": RECIPIENT, "value": str(SEND_WEI), "chain_id": CHAIN_ID}
    )
    executed = wallet.mcp.tool("execute_transaction", {"preview_id": preview["preview_id"]})
    assert executed["state"] == "executed"
    transaction = chain.anvil.transaction(executed["tx_hash"])
    assert transaction is not None
    assert transaction["to"].lower() == RECIPIENT.lower()
    assert int(transaction["value"], 16) == SEND_WEI
    after = observed(chain, wallet)
    assert after[0] == before[0] + SEND_WEI
    assert int(after[1], 16) == int(before[1], 16) + 1
    replay = wallet.mcp.tool("execute_transaction", {"preview_id": preview["preview_id"]})
    assert replay["tx_hash"] == executed["tx_hash"]
    assert observed(chain, wallet) == after


@pytest.mark.parametrize("policy", ["read_only", "supervised", "autonomous"])
def test_http_signing_reaches_core_and_is_refused_in_every_policy(
    wallet: Wallet, chain: Chain, policy: str
) -> None:
    mode(wallet, policy)
    before = observed(chain, wallet)
    for path, payload in (
        ("sign_message", {"message": "probe", "sign_type": "eip191"}),
        (
            "sign_typed_data",
            {"domain_separator": "0x" + "11" * 32, "struct_hash": "0x" + "22" * 32},
        ),
    ):
        answer = http(wallet, f"/api/v1/wallet/{path}", payload)
        assert answer["status"] == 409, answer
        assert answer["body"]["error"] == "tx_blocked", answer
        assert "signature" not in answer["body"]
    assert observed(chain, wallet) == before


def restart(
    wallet: Wallet, chain: Chain, image: str, tmp_path: Path, capabilities: str | None
) -> None:
    wallet.mcp.close()
    wallet.mcp = start_wallet(
        image,
        chain.network,
        wallet.volume,
        wallet.name,
        chain.url_from_container,
        tmp_path / f"{uuid.uuid4().hex}.stderr.log",
        capabilities=capabilities,
    )


def test_implicit_ceiling_rejects_raw_mcp_and_http_writes(
    wallet: Wallet, chain: Chain, image: str, tmp_path: Path
) -> None:
    restart(wallet, chain, image, tmp_path, None)
    before = observed(chain, wallet)
    tools = wallet.mcp.call("tools/list", {})
    assert {tool["name"] for tool in tools["tools"]} == {
        "get_wallet_context",
        "get_balances",
        "get_positions",
    }
    for tool in ("preview_transaction", "execute_transaction", "get_execution_status"):
        with pytest.raises(RuntimeError, match="requires additional capability"):
            wallet.mcp.tool(tool, {})
    for route in ("preview_transaction", "execute_transaction", "sign_message", "sign_typed_data"):
        assert http(wallet, f"/api/v1/wallet/{route}", {})["status"] == 403
    assert http(wallet, "/health", None)["status"] == 200
    assert observed(chain, wallet) == before


def test_update_wiring_leaves_a_live_wallet_and_persisted_policy_untouched(
    wallet: Wallet, image: str, tmp_path: Path
) -> None:
    """Real live state, stubbed release transport/signatures; not provenance proof."""
    mode(wallet, "supervised")
    before = wallet.mcp.tool("get_wallet_context", {})
    policy = wallet.exec("cat", "/data/policy.json").stdout
    home, assets, bin_dir = (tmp_path / name for name in ("home", "assets", "bin"))
    for path in (home, assets, bin_dir):
        path.mkdir()
    config = home / ".config/rustok"
    config.mkdir(parents=True)
    (config / "config").write_text("engine=podman\n")
    record = home / ".local/share/rustok"
    record.mkdir(parents=True)
    installer = ROOT / "scripts/install.sh"
    digest = re.search(r'^WALLET_DIGEST="([^"]+)"$', installer.read_text(), re.MULTILINE)
    assert digest
    manifest = (
        "format=rustok-wallet-release-v1\nwallet_version=0.12.0\nsource_commit="
        + "1" * 40
        + "\nimage_ref=ghcr.io/rustok-org/rustok-wallet-tui@"
        + digest[1]
        + "\ninstaller_sha256="
        + hashlib.sha256(installer.read_bytes()).hexdigest()
        + "\nshim_sha256="
        + hashlib.sha256((ROOT / "cli/rustok").read_bytes()).hexdigest()
        + "\n"
    )
    (record / "release.manifest").write_text(manifest)
    (assets / "release.manifest").write_text(manifest)
    (assets / "release.manifest.sigstore.json").write_text("{}\n")
    shutil.copyfile(installer, assets / "install.sh")
    for tool in (
        "sh",
        "cat",
        "grep",
        "sed",
        "tail",
        "od",
        "tr",
        "cut",
        "mkdir",
        "rm",
        "mv",
        "cp",
        "chmod",
        "rmdir",
        "mktemp",
        "sha256sum",
        "env",
        "sort",
        "head",
        "awk",
        "jq",
    ):
        real = shutil.which(tool)
        assert real, tool
        (bin_dir / tool).symlink_to(real)
    verifier = bin_dir / "cosign"
    verifier.write_text('#!/bin/sh\n[ "$1" != version ] || echo "GitVersion: v3.0.3"\nexit 0\n')
    engine = bin_dir / "podman"
    real_engine = shutil.which("podman")
    assert real_engine
    engine.write_text(f'#!/bin/sh\n[ "$1" != pull ] || exit 0\nexec {engine_command()} "$@"\n')
    downloader = bin_dir / "curl"
    downloader.write_text(
        f"#!{sys.executable}\nimport pathlib,shutil,sys\n"
        'url=next(arg for arg in sys.argv if arg.startswith("https://"))\n'
        'out=sys.argv[sys.argv.index("-o")+1]\n'
        f'source=pathlib.Path({str(ROOT / "cli/rustok")!r}) if url.endswith("/cli/rustok") '
        f'else pathlib.Path({str(assets)!r})/url.rsplit("/",1)[1]\n'
        "shutil.copyfile(source,out)\n"
    )
    for tool in (verifier, engine, downloader):
        tool.chmod(0o755)
    env = {"HOME": str(home), "PATH": str(bin_dir), "SHELL": "/bin/bash"}
    updated = subprocess.run(  # noqa: S603 — fixed shim, isolated host and fixture assets
        ["/bin/sh", str(ROOT / "cli/rustok"), "update"],
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert "Existing live sessions keep their previous image/grants" in updated.stdout
    inspected = json.loads(podman("inspect", wallet.name).stdout)[0]
    assert inspected["State"]["Running"]
    assert inspected["Image"].removeprefix("sha256:") == image.removeprefix("sha256:")
    after = wallet.mcp.tool("get_wallet_context", {})
    assert after["address"] == before["address"]
    assert after["policy_mode"] == before["policy_mode"]
    assert wallet.exec("cat", "/data/policy.json").stdout == policy


def test_active_human_execution_finishes_before_stop_and_restart_preserves_policy(
    wallet: Wallet, chain: Chain, image: str, tmp_path: Path
) -> None:
    mode(wallet, "supervised")
    policy_before = wallet.exec("cat", "/data/policy.json").stdout
    before = observed(chain, wallet)
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)
    assert observed(chain, wallet) == before, "supervised parking must not broadcast"
    # The Release audit row is written after take_for_execution and before
    # network I/O. Observe it, then prove deny sees InFlight while RPC is paused.
    with ThreadPoolExecutor(max_workers=1) as pool:
        podman("pause", chain.container)
        future = pool.submit(human, wallet, {"op": "approve", "id": preview_id, "pin": wallet.pin})
        try:
            deadline = time.monotonic() + 8
            while True:
                probe = wallet.exec(
                    "python3",
                    "-c",
                    "import sqlite3,sys; db=sqlite3.connect('file:/home/rustok/.rustok/agent/audit.db?mode=ro',uri=True); "
                    "print(db.execute('select count(*) from audit_log where action=? and preview_id=?',"
                    "('release',sys.argv[1])).fetchone()[0])",
                    preview_id,
                )
                if int(probe.stdout) > 0:
                    break
                assert time.monotonic() < deadline, "human execution never entered release"
                time.sleep(0.1)
            in_flight = human(wallet, {"op": "deny", "id": preview_id})[0]
            assert in_flight == {"ok": False, "error": "already_resolved", "state": "pending"}
        finally:
            podman("unpause", chain.container)
        approved = future.result(timeout=30)[0]
    assert approved["ok"] and approved["state"] == "executed", approved
    terminal = wait_status(wallet, preview_id, "executed")
    assert chain.anvil.transaction(terminal["tx_hash"]) is not None
    assert observed(chain, wallet)[0] == before[0] + SEND_WEI

    # Stop uses the real shim, real engine and a human terminal. The local
    # candidate override is explicit; this is not a signed-release assertion.
    data = tmp_path / "data/rustok"
    data.mkdir(parents=True)
    digest = hashlib.sha256((ROOT / "scripts/install.sh").read_bytes()).hexdigest()
    (data / "release.manifest").write_text(
        "format=rustok-wallet-release-v1\nwallet_version=0.12.0\n"
        + "source_commit="
        + "1" * 40
        + "\n"
        + "image_ref=ghcr.io/rustok-org/rustok-wallet-tui@sha256:"
        + "a" * 64
        + "\n"
        + f"installer_sha256={digest}\nshim_sha256="
        + "b" * 64
        + "\n"
    )
    home = tmp_path / "home"
    home.mkdir()
    config = tmp_path / "config/rustok"
    config.mkdir(parents=True)
    (config / "config").write_text("engine=podman\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    engine = bin_dir / "podman"
    engine.write_text(f'#!/bin/sh\nexec {engine_command()} "$@"\n')
    engine.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "RUSTOK_IMAGE": image,
        "PATH": str(bin_dir) + ":" + os.environ["PATH"],
    }
    stopped = subprocess.run(  # noqa: S603 — fixed fixture scripts and argv, no shell
        [
            sys.executable,
            str(ROOT / "tests/shim/pty-init.py"),
            "sh",
            str(ROOT / "cli/rustok"),
            "stop",
            "--agent",
            wallet.name,
        ],
        input="FINISHED\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=40,
        check=False,
    )
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "wallet stopped" in stopped.stdout
    # The real shim already terminated the previous process/container. Close
    # its client exactly once before replacing it; cleanup uses the new client.
    restart(wallet, chain, image, tmp_path, "read_wallet,preview_tx,execute_tx")
    context = wallet.mcp.tool("get_wallet_context", {})
    assert context["address"].lower() == wallet.address.lower()
    assert wallet.exec("cat", "/data/policy.json").stdout == policy_before
    with pytest.raises(RuntimeError, match="no parked execution|not found"):
        wallet.status(preview_id)
    assert observed(chain, wallet)[0] == before[0] + SEND_WEI


@pytest.mark.e2e_slow
def test_expired_preview_cannot_be_executed(wallet: Wallet, chain: Chain) -> None:
    preview = wallet.mcp.tool(
        "preview_transaction", {"to": RECIPIENT, "value": str(SEND_WEI), "chain_id": CHAIN_ID}
    )
    before = observed(chain, wallet)
    time.sleep(305)  # Real production PreviewCache TTL; no test-only core knob.
    with pytest.raises(RuntimeError, match="expired or unknown"):
        wallet.mcp.tool("execute_transaction", {"preview_id": preview["preview_id"]})
    assert observed(chain, wallet) == before
