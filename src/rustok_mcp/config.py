"""Application settings via pydantic-settings."""

from functools import lru_cache
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
    # Inbound bearer secret clients must present to MCP (RUSTOK_MCP_INBOUND_API_KEY).
    # Distinct trust boundary from api_key; empty string normalizes to None.
    inbound_api_key: Annotated[str | None, BeforeValidator(_empty_to_none)] = None
    # Capabilities granted to the process-trusted stdio transport
    # (RUSTOK_MCP_CAPABILITIES). Unset → all (stdio is not a security boundary);
    # a comma-separated subset restricts it (e.g. "read_wallet" for a read-only
    # agent). The network-facing SSE transport ignores this and stays gated.
    capabilities: Annotated[str | None, BeforeValidator(_empty_to_none)] = None

    model_config = SettingsConfigDict(env_prefix="RUSTOK_MCP_")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings instance.

    Use in tests when monkeypatching environment variables.
    """
    get_settings.cache_clear()
