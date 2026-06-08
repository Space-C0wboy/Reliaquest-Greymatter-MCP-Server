"""Async GraphQL client for the ReliaQuest GreyMatter API."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import Config, get_config
from .errors import GreyMatterAPIError, GreyMatterGraphQLError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_MAX_RETRY_AFTER_SECONDS = 60.0


def _parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None
    value = header_value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class GreyMatterClient:
    """Thin async wrapper over the single GreyMatter GraphQL endpoint.

    Auth: every request sends `X-API-KEY`. Multi-OpCo accounts may set the
    `x-reliaquest-customer` header (default from config, overridable per call).
    """

    def __init__(self, config: Config | None = None):
        self._config = config or get_config()
        self._client: httpx.AsyncClient | None = None
        self._connect_lock = asyncio.Lock()

    async def __aenter__(self) -> GreyMatterClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url="",
                    timeout=self._config.timeout,
                    headers={
                        "X-API-KEY": self._config.api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "greymatter-mcp/0.1.0",
                    },
                )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self, customer_slug: str | None) -> dict[str, str]:
        slug = customer_slug or self._config.customer_slug
        return {"x-reliaquest-customer": slug} if slug else {}

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        customer_slug: str | None = None,
    ) -> Any:
        """Run a GraphQL document and return its `data` object.

        Raises GreyMatterGraphQLError if the response carries an `errors` array,
        GreyMatterAPIError on transport/HTTP failures. Retries transient errors
        (429/5xx/network) with exponential backoff + jitter, honoring Retry-After.
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None

        payload = {"query": query, "variables": variables or {}}
        headers = self._headers(customer_slug)

        next_backoff: float | None = None
        for attempt in range(_MAX_RETRIES):
            if next_backoff is not None:
                logger.warning(
                    "Retry %d/%d — backing off %.2fs", attempt, _MAX_RETRIES - 1, next_backoff
                )
                await asyncio.sleep(next_backoff)
                next_backoff = None

            try:
                response = await self._client.post(
                    self._config.base_url, json=payload, headers=headers
                )
            except httpx.HTTPError as e:
                if attempt == _MAX_RETRIES - 1:
                    raise GreyMatterAPIError(0, f"Network error: {e}") from e
                logger.warning("Network error on attempt %d: %s", attempt + 1, e)
                next_backoff = random.uniform(0, 2**attempt)
                continue

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                next_backoff = (
                    min(retry_after, _MAX_RETRY_AFTER_SECONDS)
                    if retry_after is not None
                    else random.uniform(0, 2**attempt)
                )
                logger.warning("HTTP %d — will retry", response.status_code)
                continue

            if response.status_code >= 400:
                try:
                    body: Any = response.json()
                except ValueError:
                    body = response.text
                message = (
                    body.get("message") or body.get("error") or str(body)
                    if isinstance(body, dict)
                    else str(body)
                )
                raise GreyMatterAPIError(response.status_code, message, body)

            try:
                parsed = response.json()
            except ValueError as e:
                raise GreyMatterAPIError(
                    response.status_code, f"Non-JSON response: {e}", response.text
                ) from e

            errors = parsed.get("errors") if isinstance(parsed, dict) else None
            if errors:
                raise GreyMatterGraphQLError(errors, data=parsed.get("data"))
            return parsed.get("data") if isinstance(parsed, dict) else parsed

        raise GreyMatterAPIError(0, "Max retries exceeded")  # pragma: no cover


_client: GreyMatterClient | None = None
_client_lock = asyncio.Lock()


async def get_client() -> GreyMatterClient:
    """Return a process-wide shared client (one connection pool)."""
    global _client
    async with _client_lock:
        if _client is None:
            _client = GreyMatterClient()
            await _client.connect()
    return _client


async def shutdown_client() -> None:
    global _client
    async with _client_lock:
        if _client is not None:
            await _client.close()
            _client = None
