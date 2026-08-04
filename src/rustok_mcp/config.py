"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _empty_to_none(value: str | None) -> str | None:
    """Treat a set-but-empty env var as unset.

    ``RUSTOK_MCP_INBOUND_API_KEY=`` must never read as enabled auth, otherwise
    an empty value would be mistaken for a configured key (and could match an
    empty client token). Blank/whitespace-only collapses to ``None``.
    """
    if value is None:
        return None
    return value.strip() or None


class Settings(BaseSettings):
    """MCP server configuration loaded from environment."""

    app_name: str = "rustok-mcp"
    host: str = "127.0.0.1"
    port: int = 3001
    gateway_url: str = "http://127.0.0.1:3000"
    log_level: str = "INFO"
    # Outbound key for MCP -> Gateway calls (RUSTOK_MCP_API_KEY).
    api_key: str | None = None
    # Path to a file holding that key (RUSTOK_MCP_API_KEY_FILE). The delivery the
    # container entrypoint uses, and the one we document: the value then lives in
    # no process environment. Read via resolve_outbound_api_key below.
    api_key_file: Annotated[str | None, BeforeValidator(_empty_to_none)] = None
    # Inbound bearer secret clients must present to MCP (RUSTOK_MCP_INBOUND_API_KEY).
    # Distinct trust boundary from api_key; empty string normalizes to None.
    inbound_api_key: Annotated[str | None, BeforeValidator(_empty_to_none)] = None
    # Capabilities granted to the process-trusted stdio transport
    # (RUSTOK_MCP_CAPABILITIES). Unset → all (stdio is not a security boundary);
    # a comma-separated subset restricts it (e.g. "read_wallet" for a read-only
    # agent). A set value also seeds SSE sessions (audit B1); unset, SSE keeps
    # its historical contract — gated until the first initialize grants.
    capabilities: Annotated[str | None, BeforeValidator(_empty_to_none)] = None

    model_config = SettingsConfigDict(env_prefix="RUSTOK_MCP_")


def resolve_outbound_api_key(settings: Settings) -> str | None:
    """The bearer key MCP presents to the gateway.

    ``RUSTOK_MCP_API_KEY_FILE`` wins when set. The container entrypoint stages
    the key in a ``0600`` file and exports only its path, so the value is in no
    process's ``/proc/<pid>/environ`` and in no ``podman inspect`` output — the
    same ``_FILE`` convention the keyring password uses. Trailing newlines are
    stripped, so a key written by ``printf`` and one written by an editor are
    the same key.

    Args:
        settings: The loaded configuration.

    Returns:
        The key, or ``None`` when neither variable is set (dev, unauthenticated).

    Raises:
        ValueError: The named file cannot be read, or holds nothing but line
            endings. Deliberately fatal rather than falling back to "no key":
            a wrong path must fail loudly at startup, not turn every later call
            into an unexplained gateway error.
    """
    if settings.api_key_file is None:
        return settings.api_key
    path = Path(settings.api_key_file)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"RUSTOK_MCP_API_KEY_FILE is not readable: {path}") from exc
    key = raw.rstrip("\r\n")
    if not key:
        raise ValueError(f"RUSTOK_MCP_API_KEY_FILE is empty: {path}")
    return key


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings instance.

    Use in tests when monkeypatching environment variables.
    """
    get_settings.cache_clear()
