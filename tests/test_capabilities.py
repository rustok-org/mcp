"""Capability model tests."""

from rustok_mcp.capabilities import (
    CAPABILITY_MAP,
    Capability,
    Session,
    has_capability,
    parse_capabilities,
)


def test_capability_enum_values() -> None:
    """Capability enum contains expected members."""
    assert Capability.READ_WALLET == "read_wallet"
    assert Capability.PREVIEW_TX == "preview_tx"
    assert Capability.EXECUTE_TX == "execute_tx"


def test_capability_map() -> None:
    """CAPABILITY_MAP covers all stub tools."""
    assert CAPABILITY_MAP["get_wallet_context"] == Capability.READ_WALLET
    assert CAPABILITY_MAP["get_balances"] == Capability.READ_WALLET
    assert CAPABILITY_MAP["preview_send"] == Capability.PREVIEW_TX
    assert CAPABILITY_MAP["execute_send"] == Capability.EXECUTE_TX
    assert CAPABILITY_MAP["sign_message"] == Capability.EXECUTE_TX


def test_parse_capabilities_valid() -> None:
    """parse_capabilities converts strings to Capability set."""
    caps = parse_capabilities(["read_wallet", "preview_tx"])
    assert caps == {Capability.READ_WALLET, Capability.PREVIEW_TX}


def test_parse_capabilities_skips_unknown() -> None:
    """Unknown capability strings are silently ignored."""
    caps = parse_capabilities(["read_wallet", "admin_mode", "preview_tx"])
    assert caps == {Capability.READ_WALLET, Capability.PREVIEW_TX}


def test_parse_capabilities_empty() -> None:
    """Empty input yields empty set."""
    assert parse_capabilities([]) == set()


def test_has_capability_with_required() -> None:
    """has_capability returns True only when required capability is present."""
    caps = {Capability.READ_WALLET}
    assert has_capability("get_wallet_context", caps) is True
    assert has_capability("execute_send", caps) is False


def test_has_capability_unmapped_tool() -> None:
    """Unmapped tools are denied by default (fail-closed)."""
    assert has_capability("unknown_tool", set()) is False
    assert has_capability("unknown_tool", {Capability.READ_WALLET}) is False


def test_session_default_capabilities() -> None:
    """Session defaults to empty capabilities."""
    session = Session(session_id="test")
    assert session.capabilities == set()
    assert session.queue is None


def test_session_with_queue() -> None:
    """Session can be created with a queue."""
    import asyncio

    queue: asyncio.Queue[str] = asyncio.Queue()
    session = Session(session_id="test", queue=queue)
    assert session.queue is queue
