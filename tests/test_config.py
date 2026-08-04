"""Settings / configuration tests."""

from pathlib import Path

import pytest

from rustok_mcp.config import Settings, resolve_outbound_api_key


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


def test_capabilities_read_from_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """capabilities is read from RUSTOK_MCP_CAPABILITIES."""
    monkeypatch.setenv("RUSTOK_MCP_CAPABILITIES", "read_wallet,preview_tx")
    assert Settings().capabilities == "read_wallet,preview_tx"


def test_capabilities_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """capabilities defaults to None when unset (stdio then grants all)."""
    monkeypatch.delenv("RUSTOK_MCP_CAPABILITIES", raising=False)
    assert Settings().capabilities is None


def test_capabilities_empty_string_normalizes_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set-but-empty value reads as unset (→ all caps), never as a blank set."""
    monkeypatch.setenv("RUSTOK_MCP_CAPABILITIES", "")
    assert Settings().capabilities is None


def test_outbound_key_falls_back_to_the_plain_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No file named → the key comes from RUSTOK_MCP_API_KEY as it always did."""
    monkeypatch.delenv("RUSTOK_MCP_API_KEY_FILE", raising=False)
    monkeypatch.setenv("RUSTOK_MCP_API_KEY", "from-env")
    assert resolve_outbound_api_key(Settings()) == "from-env"


@pytest.mark.parametrize("written", ["from-file", "from-file\n", "from-file\r\n"])
def test_outbound_key_reads_the_file_and_strips_line_endings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    written: str,
) -> None:
    """A key written by printf and one written by an editor are the same key."""
    key_file = tmp_path / "gateway-key"
    key_file.write_text(written, encoding="utf-8")
    monkeypatch.setenv("RUSTOK_MCP_API_KEY_FILE", str(key_file))
    assert resolve_outbound_api_key(Settings()) == "from-file"


def test_outbound_key_file_wins_over_the_plain_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The file is the documented delivery, so it takes precedence.

    Otherwise a stale RUSTOK_MCP_API_KEY left in the environment would quietly
    win over the staged file and the gateway would reject every call.
    """
    key_file = tmp_path / "gateway-key"
    key_file.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("RUSTOK_MCP_API_KEY_FILE", str(key_file))
    monkeypatch.setenv("RUSTOK_MCP_API_KEY", "from-env")
    assert resolve_outbound_api_key(Settings()) == "from-file"


@pytest.mark.parametrize("written", ["", "\n"])
def test_outbound_key_file_that_is_empty_is_fatal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    written: str,
) -> None:
    """An empty file must not read as "no key" — that starts an unauthenticated MCP."""
    key_file = tmp_path / "gateway-key"
    key_file.write_text(written, encoding="utf-8")
    monkeypatch.setenv("RUSTOK_MCP_API_KEY_FILE", str(key_file))
    with pytest.raises(ValueError, match="is empty"):
        resolve_outbound_api_key(Settings())


def test_outbound_key_file_that_is_missing_is_fatal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A wrong path fails loudly at startup, not as an unexplained 401 later."""
    monkeypatch.setenv("RUSTOK_MCP_API_KEY_FILE", str(tmp_path / "absent"))
    with pytest.raises(ValueError, match="is not readable"):
        resolve_outbound_api_key(Settings())
