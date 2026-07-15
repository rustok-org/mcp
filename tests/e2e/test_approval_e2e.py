"""Acceptance: the approval channel, end to end, against the SHIPPED wallet image.

The agent proposes over MCP stdio; the human decides in a real terminal (a pty running
the console); the core signs and broadcasts. Nothing here is mocked — the only thing
that is local is the chain.

Scenario numbering follows the Stage-6 spec (`.claude/specs/2026-07-11-stage6-e2e-acceptance.md`).
"""

from __future__ import annotations

import re
import time
from typing import Any

import pytest

from tests.e2e.conftest import Chain
from tests.e2e.console import Console
from tests.e2e.wallet import SOCKET_PATH, Wallet

pytestmark = pytest.mark.e2e

# anvil's deterministic accounts: a recipient, and a "token" + "spender" for the
# approve card. The approve target needs no bytecode — the core decodes the call
# offline (core `simulate::decode_builder_call`), which is exactly why an unlimited
# approval can be shown to the human even with no RPC in reach.
RECIPIENT = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ERC20_CONTRACT = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
SPENDER = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"
SEND_WEI = 1_000_000_000_000_000  # 0.001 ETH

# v0.2 outcome notice (console `ui.rs::notice_line`): "APPROVED — 0x<tx hash>".
_EXECUTED_HASH_RE = re.compile(r"APPROVED\s+—\s+(0x[0-9a-fA-F]{64})")
# The resident session's normal end (console `main.rs::EXIT_ABORTED`): decisions
# are notices on a living console, `q` is the only everyday way out (ADR #7).
EXIT_ABORTED = 6


def wait_status(
    wallet: Wallet, preview_id: str, expected: str, timeout: float = 60
) -> dict[str, Any]:
    """Poll the agent-side status until it reaches `expected` (the human is deciding)."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = wallet.status(preview_id)
        if last["state"] == expected:
            return last
        time.sleep(0.5)
    raise AssertionError(f"status never became {expected!r}; last answer: {last}")


def unlock_to_queue(console: Console, wallet: Wallet, pending: int = 1) -> None:
    """Walk the console to the queue with the parked item(s) on screen.

    v0.2 home is the Dashboard; the tab bar rides every view and carries the
    live queue count, so it doubles as the "item arrived" signal. The row
    itself (`… wei`) must be on screen before Enter can open a card.
    """
    console.wait_for_text("PIN")
    console.submit_pin(wallet.pin)
    console.wait_for_text(f"Queue·{pending} [a]")
    console.send("a")
    console.wait_for_text(" wei")


def unlock_and_open_card(console: Console, wallet: Wallet, pending: int = 1) -> None:
    """Walk the console to an open clear-signing card."""
    unlock_to_queue(console, wallet, pending)
    console.send("\r")
    console.wait_for_text("Approve ]")


def assert_resident(console: Console, remaining: int) -> None:
    """The v0.2 heart: a decision is a notice on a LIVING console, not an exit.

    The card closed, the queue count dropped to `remaining`, and the process is
    still there — a console that dies on a decision is the v0.1 regression this
    suite exists to catch now.
    """
    assert console.is_alive(), "the resident console must survive a decision (ADR #7)"
    console.wait_for_text(f"Queue·{remaining} [a]")


def test_s0_socket_lives_on_podman_tmpfs_and_the_console_connects(wallet: Wallet) -> None:
    """S0: /run is a tmpfs under podman — the entrypoint must recreate the socket dir."""
    probe = wallet.exec("test", "-S", SOCKET_PATH, check=False)
    assert probe.returncode == 0, f"{SOCKET_PATH} is not a socket inside the container"

    with Console(wallet.name) as console:
        # Reaching the PIN screen means the `hello` handshake crossed the socket.
        console.wait_for_text("Enter your wallet PIN")


def test_s1_approve_broadcasts_and_both_sides_see_the_same_tx_hash(
    wallet: Wallet, chain: Chain
) -> None:
    """S1: park -> PIN -> `y` -> executed; the agent's hash is the chain's hash."""
    recipient_before = chain.anvil.balance(RECIPIENT)
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    with Console(wallet.name) as console:
        unlock_and_open_card(console, wallet)
        console.send("y")
        console.wait_for_text("APPROVED — 0x")
        screen = console.screen
        assert_resident(console, remaining=0)
        exit_code = console.quit()

    match = _EXECUTED_HASH_RE.search(screen)
    assert match, f"the console never showed the executed tx hash:\n{screen}"
    console_hash = match.group(1).lower()
    assert exit_code == EXIT_ABORTED, "quitting the resident session must exit 6 (EXIT_ABORTED)"

    status = wait_status(wallet, preview_id, "executed")
    assert status["tx_hash"].lower() == console_hash, (
        "the human and the agent must see the SAME transaction — "
        f"console {console_hash}, agent {status['tx_hash']}"
    )

    onchain = chain.anvil.transaction(console_hash)
    assert onchain is not None, "the approved transaction never reached the chain"
    assert onchain["to"].lower() == RECIPIENT.lower()
    assert int(onchain["value"], 16) == SEND_WEI
    assert chain.anvil.balance(RECIPIENT) == recipient_before + SEND_WEI, (
        "the money did not actually arrive — a hash on screen is not a settled transfer"
    )


def test_s2_deny_resolves_as_denied_and_nothing_is_broadcast(wallet: Wallet) -> None:
    """S2: the human says no — the agent sees `denied`, no money moves."""
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    with Console(wallet.name) as console:
        unlock_and_open_card(console, wallet)
        console.send("n")
        console.wait_for_text("REJECTED")
        assert_resident(console, remaining=0)
        exit_code = console.quit()

    assert exit_code == EXIT_ABORTED, "quitting the resident session must exit 6 (EXIT_ABORTED)"
    status = wait_status(wallet, preview_id, "denied")
    assert status["tx_hash"] is None, "a denied transaction must carry no tx hash"


def test_s4_three_wrong_pins_lock_the_channel_and_fail_the_queue_closed(wallet: Wallet) -> None:
    """S4: the lockout ladder is cumulative, and it resolves the queue to `denied`.

    Shipped semantics (core `approval.rs::drop_all_pending`): a lockout does not delete
    the queue, it RESOLVES every pending item to `denied` — fail-closed, and still
    queryable by the agent. The function is called `drop_pending_on_lockout`; the
    behaviour is denial.
    """
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    with Console(wallet.name) as console:
        console.wait_for_text("PIN")
        for attempts_left in (2, 1, 0):
            console.submit_pin("000000")
            console.wait_for_text(f"Wrong PIN — {attempts_left} attempt(s) left.")

        # The ladder armed on the "0 attempts left" answer; the NEXT attempt is the
        # first one to be refused outright.
        console.submit_pin("000000")
        console.wait_for_text("Locked out.")

    status = wait_status(wallet, preview_id, "denied")
    assert status["tx_hash"] is None, "a locked-out queue must not leave anything signable"


def test_s5_unlimited_approve_card_shows_the_danger_and_gates_on_the_pin(wallet: Wallet) -> None:
    """S5: the drain vector — the card must SHOW `UNLIMITED` and refuse a bare `y`."""
    preview_id = wallet.park_unlimited_approve(ERC20_CONTRACT, SPENDER)

    with Console(wallet.name) as console:
        unlock_and_open_card(console, wallet)
        card = console.screen
        # Phase-1 card language: "⚠ HIGH RISK  <reasons>" and "amount  UNLIMITED".
        assert "HIGH RISK" in card and "unlimited_approval" in card, (
            f"the risk was not shouted:\n{card}"
        )
        assert "amount  UNLIMITED" in card, f"the card hid the unlimited allowance:\n{card}"
        assert "decoded_call.method: approve" in card
        assert SPENDER.lower() in card.lower(), "the human must see WHO is being authorized"

        # `y` on a high-risk card sends nothing: it opens the per-tx PIN prompt
        # (console `app.rs::on_approve`). The gate is client-side here — the server's
        # own `pin_required` is proven separately, below.
        console.send("y")
        console.wait_for_text("High-risk approval — enter your PIN:")

        console.submit_pin(wallet.pin)
        console.wait_for_text("APPROVED")
        assert_resident(console, remaining=0)
        exit_code = console.quit()

    assert exit_code == EXIT_ABORTED
    status = wait_status(wallet, preview_id, "executed")
    assert status["tx_hash"] is not None


def test_s5_server_refuses_a_high_risk_approve_without_a_pin(wallet: Wallet) -> None:
    """S5 (server half): `pin_required` — a response the console cannot even provoke."""
    preview_id = wallet.park_unlimited_approve(ERC20_CONTRACT, SPENDER)

    hello, auth, approve = wallet.socket_ops(
        [
            {"op": "hello", "proto": 1, "client": "rustok-e2e/1"},
            {"op": "auth", "pin": wallet.pin},
            {"op": "approve", "id": preview_id},
        ]
    )

    assert hello["ok"] is True
    assert auth["ok"] is True
    assert approve == {"ok": False, "error": "pin_required"}, (
        f"a high-risk approve without a PIN must be refused, got {approve}"
    )
    assert wallet.status(preview_id)["state"] == "pending", (
        "a refused approve must leave the item parked, not resolved"
    )


def test_s6_a_pipe_can_never_approve(wallet: Wallet) -> None:
    """S6: no tty, no approval (console invariant #4) — `docker exec -i` is view-only."""
    done = wallet.exec("rustok-console", check=False)

    assert done.returncode == 3, f"a piped console must exit 3 (EXIT_NO_TTY), got {done.returncode}"
    assert "needs an interactive terminal" in done.stderr
    assert "Approval from a pipe is never accepted." in done.stderr


def test_s7_approve_without_auth_is_unauthorized(wallet: Wallet) -> None:
    """S7: the socket's own gate — no `auth`, no decision, however well-formed the ask."""
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    hello, approve, deny = wallet.socket_ops(
        [
            {"op": "hello", "proto": 1, "client": "rustok-e2e/1"},
            {"op": "approve", "id": preview_id},
            {"op": "deny", "id": preview_id},
        ]
    )

    assert hello["ok"] is True
    assert approve == {"ok": False, "error": "unauthorized"}, (
        f"approve slipped past auth: {approve}"
    )
    assert deny == {"ok": False, "error": "unauthorized"}, f"deny slipped past auth: {deny}"
    assert wallet.status(preview_id)["state"] == "pending", "the item must still be parked"


def test_s8_a_rejected_broadcast_surfaces_as_failed_on_both_sides(wallet: Wallet) -> None:
    """S8: approved, but the chain said no — the agent's polling contract owes a `failed`.

    Stage 5 published `executed/denied/expired/failed` + `error_reason` to agents. Two
    previews taken before either is broadcast BOTH carry nonce 0 (the nonce is frozen in
    the preview — core `pipeline::execute` signs `nonce: preview.nonce`), so approving
    the second one after the first is mined is rejected by the chain. Nothing is mocked:
    the failure comes from the node.
    """
    first_id = wallet.park_send(RECIPIENT, SEND_WEI)
    second_id = wallet.park_send(RECIPIENT, SEND_WEI)

    with Console(wallet.name) as console:
        unlock_and_open_card(console, wallet, pending=2)
        console.send("y")
        console.wait_for_text("APPROVED")
        assert_resident(console, remaining=1)
        assert console.quit() == EXIT_ABORTED

    # The queue order is not deterministic (the core stores pending items in a map), so
    # the second console approves whichever item is left — the outcome is what matters.
    with Console(wallet.name) as console:
        unlock_and_open_card(console, wallet, pending=1)
        console.send("y")
        console.wait_for_text("FAILED — ")
        # v0.2: a failed broadcast is an OUTCOME (a notice), not a fatal — the
        # console lives on and the human keeps working the queue (ADR #7).
        assert_resident(console, remaining=0)
        exit_code = console.quit()

    assert exit_code == EXIT_ABORTED, (
        f"a failed broadcast is a notice, not a fatal — quitting must exit 6, got {exit_code}"
    )

    outcomes = {wallet.status(first_id)["state"], wallet.status(second_id)["state"]}
    assert outcomes == {"executed", "failed"}, (
        f"one send must land and the stale-nonce one must fail, got {outcomes}"
    )
    failed = next(
        status
        for status in (wallet.status(first_id), wallet.status(second_id))
        if status["state"] == "failed"
    )
    assert failed["error_reason"], "a failed execution must tell the agent WHY"
    assert failed["tx_hash"] is None, "nothing was mined — there is no hash to show"


def test_s9_a_card_the_human_cannot_read_cannot_be_approved(wallet: Wallet) -> None:
    """S9: the anti-blind-signing gate — the one invariant the rest of this suite dodges.

    Every other scenario sizes the pty at 140x50 so the card fits. That deliberately
    avoids the shipped console's own guard: while the card's priority fields do not fit
    the terminal, `y` is dead (console `ui.rs::priority_fields_fit`) — "a yes to a card
    the human could not read is not a decision". Here the guard itself is the subject.
    """
    preview_id = wallet.park_send(RECIPIENT, SEND_WEI)

    with Console(wallet.name, rows=10, cols=40) as console:
        console.wait_for_text("PIN")
        console.submit_pin(wallet.pin)
        # 40 columns clip the row's "… wei" tail; the tab count and the kind
        # word are the anchors that survive a small terminal.
        console.wait_for_text("Queue·1 [a]")
        console.send("a")
        console.wait_for_text("send")
        console.send("\r")
        console.wait_for_text("TOO SMALL")

        console.send("y")
        # `y` must be inert. Give the console more than its own 2.5 s poll cycle to prove
        # it: if the keystroke were going to resolve anything, it would have by now.
        time.sleep(4)
        assert wallet.status(preview_id)["state"] == "pending", (
            "the console approved a card the human could not read"
        )

        # Saying NO stays available even on a screen too small to read the card.
        # At 40x10 the notice line itself does not fit the layout (the queue and
        # card panels take every row), so the REJECTED banner cannot be the
        # anchor here — the machine truth (agent-side status) and the emptied
        # queue are. The notice IS asserted on full-size screens in s2.
        console.send("n")
        wait_status(wallet, preview_id, "denied")
        console.wait_for_text("Queue·0 [a]")
        assert console.is_alive(), "the resident console must survive a decision (ADR #7)"
        exit_code = console.quit()

    assert exit_code == EXIT_ABORTED, (
        f"quitting the resident session must exit 6 (EXIT_ABORTED), got {exit_code}"
    )
    assert wait_status(wallet, preview_id, "denied")["tx_hash"] is None
