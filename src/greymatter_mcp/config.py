"""Server configuration, loaded once from the environment.

Everything that controls how the MCP server connects to GreyMatter and how it
behaves is sourced from environment variables here (with optional ``.env`` support
via python-dotenv for local development). Values are parsed and validated up front
into an immutable ``Config`` dataclass, so the rest of the codebase can rely on a
single, already-validated source of truth rather than re-reading ``os.getenv``.

The public surface is:
- ``Config`` — the frozen settings object.
- ``get_config()`` — lazily builds and caches a single ``Config`` instance.
- ``reset_config_cache()`` — a test hook to force a re-read of the environment.
- ``ConfigError`` — raised for missing/invalid configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load a local .env file (if present) into os.environ at import time so that
# development setups don't have to export variables manually. In production the
# real environment already holds these values and .env is typically absent.
load_dotenv()

# Strings that count as "true" for boolean env vars (compared case-insensitively).
# Anything not in this set — including the empty string and "false"/"0" — is False.
_TRUTHY = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid.

    Distinct from runtime API errors: this signals a setup/deployment problem
    (e.g. a missing API key or a malformed URL) that must be fixed before the
    server can usefully start.
    """


@dataclass(frozen=True)
class Config:
    """Immutable, validated snapshot of the server's runtime configuration.

    Frozen so that, once built, settings can be shared freely without any risk of
    a caller mutating them mid-run. Each field maps to one environment variable
    (see ``from_env`` for the variable names, defaults, and parsing rules).
    """

    api_key: str  # GREYMATTER_API_KEY — bearer credential for the API (required)
    base_url: str  # GREYMATTER_BASE_URL — GraphQL endpoint, trailing slash trimmed
    customer_slug: str | None  # GREYMATTER_CUSTOMER_SLUG — default OpCo header, or None
    read_only: bool  # GREYMATTER_READ_ONLY — when True, mutation tools are disabled
    timeout: float  # GREYMATTER_TIMEOUT — per-request timeout in seconds
    log_level: str  # LOG_LEVEL — standard logging level name, upper-cased
    http_host: str  # MCP_HTTP_HOST — bind host for the HTTP transport
    http_port: int  # MCP_HTTP_PORT — bind port for the HTTP transport

    @classmethod
    def from_env(cls) -> Config:
        """Build a ``Config`` by reading and validating environment variables.

        Returns:
            A fully populated, frozen ``Config``.

        Raises:
            ConfigError: if the API key is missing, the base URL is malformed, or
                a numeric field cannot be parsed. Validation happens here (rather
                than lazily) so misconfiguration fails fast at startup.
        """
        # API key is mandatory — without it every request would be rejected, so we
        # refuse to construct a Config at all. .strip() guards against stray
        # whitespace from copy/paste or .env quoting.
        api_key = os.getenv("GREYMATTER_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "GREYMATTER_API_KEY is required. Set it in your environment or .env file."
            )

        # Normalize the endpoint: strip whitespace and drop any trailing slash so
        # the client can build request URLs without worrying about double slashes.
        base_url = (
            os.getenv("GREYMATTER_BASE_URL", "https://greymatter.myreliaquest.com/graphql")
            .strip()
            .rstrip("/")
        )
        # Reject anything that isn't an http(s) URL early — a typo here would
        # otherwise surface as a confusing transport error later.
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(
                f"GREYMATTER_BASE_URL must start with http:// or https:// (got {base_url!r})"
            )

        # The default OpCo (operating company) slug for the x-reliaquest-customer
        # header on multi-OpCo accounts. Empty/whitespace collapses to None so the
        # client omits the header entirely rather than sending a blank one.
        customer_slug = os.getenv("GREYMATTER_CUSTOMER_SLUG", "").strip() or None
        # Read-only mode hides mutation tools and makes graphql_query reject
        # mutations — a safety switch for read-only deployments. Defaults to off.
        read_only = os.getenv("GREYMATTER_READ_ONLY", "false").strip().lower() in _TRUTHY

        # Per-request timeout in seconds. Default of 60s is intentionally generous
        # because some GreyMatter queries are heavy. Parsed as float to allow
        # sub-second values in tests.
        try:
            timeout = float(os.getenv("GREYMATTER_TIMEOUT", "60"))
        except ValueError as e:
            raise ConfigError(f"GREYMATTER_TIMEOUT must be a number: {e}") from e

        # Logging verbosity; upper-cased so "info"/"INFO" both work with the
        # standard logging module's level names.
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        # Host/port used only when the server runs over the HTTP transport (as
        # opposed to stdio). Default host is loopback so it isn't exposed publicly
        # unless deliberately overridden.
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


# Process-wide cache for the singleton Config. None means "not yet loaded".
_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide ``Config``, building it on first use.

    The config is parsed once and memoized: every caller shares the same frozen
    instance for the life of the process. This keeps env parsing/validation out of
    hot paths and guarantees consistent settings everywhere.

    Returns:
        The cached ``Config`` (created on the first call).

    Raises:
        ConfigError: propagated from ``Config.from_env`` if configuration is bad.
    """
    global _config
    # Lazily construct on first access; subsequent calls reuse the cached value.
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config_cache() -> None:
    """Clear the cached config so the next ``get_config()`` re-reads the env.

    Intended for tests that tweak environment variables and need the change to
    take effect. Not used in normal operation, where config is meant to be stable
    for the whole process.
    """
    global _config
    _config = None
