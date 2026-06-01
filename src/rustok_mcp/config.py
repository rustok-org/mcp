"""Application settings via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP server configuration loaded from environment."""

    app_name: str = "rustok-mcp"
    port: int = 3001
    gateway_url: str = "http://127.0.0.1:3000"
    log_level: str = "INFO"
    # Read from RUSTOK_MCP_API_KEY, consistent with every other setting's prefix.
    api_key: str | None = None

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
