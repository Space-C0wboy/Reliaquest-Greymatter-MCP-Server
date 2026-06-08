"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_TRUTHY = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    customer_slug: str | None
    read_only: bool
    timeout: float
    log_level: str
    http_host: str
    http_port: int

    @classmethod
    def from_env(cls) -> Config:
        api_key = os.getenv("GREYMATTER_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "GREYMATTER_API_KEY is required. Set it in your environment or .env file."
            )

        base_url = (
            os.getenv("GREYMATTER_BASE_URL", "https://greymatter.myreliaquest.com/graphql")
            .strip()
            .rstrip("/")
        )
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(
                f"GREYMATTER_BASE_URL must start with http:// or https:// (got {base_url!r})"
            )

        customer_slug = os.getenv("GREYMATTER_CUSTOMER_SLUG", "").strip() or None
        read_only = os.getenv("GREYMATTER_READ_ONLY", "false").strip().lower() in _TRUTHY

        try:
            timeout = float(os.getenv("GREYMATTER_TIMEOUT", "60"))
        except ValueError as e:
            raise ConfigError(f"GREYMATTER_TIMEOUT must be a number: {e}") from e

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        http_host = os.getenv("MCP_HTTP_HOST", "127.0.0.1")
        try:
            http_port = int(os.getenv("MCP_HTTP_PORT", "8765"))
        except ValueError as e:
            raise ConfigError(f"MCP_HTTP_PORT must be an integer: {e}") from e

        return cls(
            api_key=api_key,
            base_url=base_url,
            customer_slug=customer_slug,
            read_only=read_only,
            timeout=timeout,
            log_level=log_level,
            http_host=http_host,
            http_port=http_port,
        )


_config: Config | None = None


def get_config() -> Config:
    """Return the lazily-loaded global config."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config_cache() -> None:
    """Test helper: clear the cached config so the next get_config() re-reads env."""
    global _config
    _config = None
