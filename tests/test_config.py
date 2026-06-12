"""Settings / configuration tests."""

import pytest

from rustok_mcp.config import Settings


def test_api_key_read_from_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_key is read from RUSTOK_MCP_API_KEY, consistent with other settings."""
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    monkeypatch.setenv("RUSTOK_MCP_API_KEY", "secret-token")
    assert Settings().api_key == "secret-token"


def test_api_key_ignores_unprefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare MCP_API_KEY (no prefix) is NOT read — locks in the prefix convention."""
    monkeypatch.delenv("RUSTOK_MCP_API_KEY", raising=False)
    monkeypatch.setenv("MCP_API_KEY", "should-be-ignored")
    assert Settings().api_key is None


def test_api_key_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_key defaults to None when unset (auth optional in dev)."""
    monkeypatch.delenv("RUSTOK_MCP_API_KEY", raising=False)
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    assert Settings().api_key is None


def test_inbound_api_key_read_from_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """inbound_api_key is read from RUSTOK_MCP_INBOUND_API_KEY."""
    monkeypatch.setenv("RUSTOK_MCP_INBOUND_API_KEY", "inbound-secret")
    assert Settings().inbound_api_key == "inbound-secret"


def test_inbound_api_key_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """inbound_api_key defaults to None when unset (auth optional in dev)."""
    monkeypatch.delenv("RUSTOK_MCP_INBOUND_API_KEY", raising=False)
    assert Settings().inbound_api_key is None


def test_inbound_api_key_empty_string_normalizes_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set-but-empty value must read as unset, never as enabled auth (D5)."""
    monkeypatch.setenv("RUSTOK_MCP_INBOUND_API_KEY", "")
    assert Settings().inbound_api_key is None


def test_inbound_api_key_whitespace_normalizes_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only value collapses to None — no accidental blank token."""
    monkeypatch.setenv("RUSTOK_MCP_INBOUND_API_KEY", "   ")
    assert Settings().inbound_api_key is None
