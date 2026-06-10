"""Async GraphQL client for the ReliaQuest GreyMatter API.

This module is the network transport layer for the MCP server. The server (see
``server.py``) and the generated tools (see ``tools``) speak to GreyMatter
exclusively through the :class:`GreyMatterClient` defined here, so that all of
the cross-cutting concerns — authentication headers, retry/backoff policy,
GraphQL error handling, and connection pooling — live in one place instead of
being scattered across every tool.

GreyMatter exposes a *single* GraphQL endpoint: every operation (query or
mutation) is an HTTP POST of ``{query, variables}`` to the same URL. That makes
the client deliberately thin — it does not know anything about specific
GraphQL documents, only how to send one safely and interpret the result.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from . import __version__
from .config import Config, get_config
from .errors import GreyMatterAPIError, GreyMatterGraphQLError

logger = logging.getLogger(__name__)

# HTTP status codes worth retrying: 429 (rate limited) plus the common 5xx
# gateway/server errors. These are treated as *transient* — the same request
# may well succeed on a later attempt — whereas a 4xx like 400/401/403 is a
# permanent client error and is surfaced immediately.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
# Total number of attempts (not retries-after-the-first); with 3 we try once
# and then retry at most twice before giving up.
_MAX_RETRIES = 3
# Upper bound on how long we are willing to honor a server-provided
# ``Retry-After`` header. Without a cap, a misbehaving or hostile upstream
# could send ``Retry-After: 86400`` and effectively park the whole MCP server
# for a day; clamping keeps us responsive.
_MAX_RETRY_AFTER_SECONDS = 60.0


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse an HTTP ``Retry-After`` header into a number of seconds to wait.

    The HTTP spec allows ``Retry-After`` in two forms, and servers use both:
    an integer count of seconds (``Retry-After: 30``) or an absolute HTTP-date
    (``Retry-After: Wed, 21 Oct 2015 07:28:00 GMT``). This helper normalizes
    both into "seconds from now" so the retry loop has a single number to work
    with.

    Args:
        header_value: The raw header string, or ``None`` if the header was
            absent.

    Returns:
        A non-negative number of seconds to wait, or ``None`` if the header was
        missing or could not be parsed (in which case the caller falls back to
        its own backoff schedule). The result is never negative even if the
        date is already in the past — we clamp to ``0.0`` so "retry now".
    """
    if not header_value:
        return None
    value = header_value.strip()
    # Fast path / most common case: a bare integer (or float) number of seconds.
    try:
        return max(0.0, float(value))
    except ValueError:
        # Not numeric — fall through and try to parse it as an HTTP-date.
        pass
    # HTTP-date form, e.g. "Wed, 21 Oct 2015 07:28:00 GMT".
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        # Unparseable garbage — treat as "no usable Retry-After".
        return None
    if when is None:
        return None
    # An HTTP-date is always UTC, but a malformed/naive datetime would break the
    # subtraction below, so backfill UTC when no tzinfo is present.
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    # Convert the absolute instant into a relative "seconds from now"; clamp so a
    # past date doesn't produce a negative sleep.
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class GreyMatterClient:
    """Thin async wrapper over the single GreyMatter GraphQL endpoint.

    One instance owns one :class:`httpx.AsyncClient` (and therefore one
    connection pool). The httpx client is created lazily on first use rather
    than in ``__init__`` because constructing it must happen inside a running
    event loop, and instances are often built before the loop is up.

    Auth: every request sends the ``X-API-KEY`` header (set once as a default
    on the underlying httpx client). Multi-OpCo ("operating company") accounts
    may additionally scope a request to one company via the
    ``x-reliaquest-customer`` header — this defaults to the slug in config but
    can be overridden per call (see :meth:`_headers` / :meth:`execute`).

    The client supports use as an async context manager and is also driven by
    the process-wide helpers :func:`get_client` / :func:`shutdown_client`.
    """

    def __init__(self, config: Config | None = None):
        # Allow an explicit Config (handy for tests) but default to the shared,
        # env-derived singleton in normal operation.
        self._config = config or get_config()
        # The real httpx client is built lazily in connect(); None means
        # "not connected yet".
        self._client: httpx.AsyncClient | None = None
        # Guards lazy connection so two coroutines racing to send the first
        # request don't each build a client (which would leak a pool).
        self._connect_lock = asyncio.Lock()

    async def __aenter__(self) -> GreyMatterClient:
        # `async with GreyMatterClient() as gm:` connects on entry...
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        # ...and always tears down the connection pool on exit, even on error.
        await self.close()

    async def connect(self) -> None:
        """Create the underlying httpx client if one does not already exist.

        Idempotent and concurrency-safe: the lock plus the ``is None`` check
        form a double-checked guard so only the first caller builds the client
        and subsequent/concurrent callers are no-ops. Headers that are constant
        for the lifetime of the client (auth, content negotiation, User-Agent)
        are set here as defaults so every request carries them automatically.
        """
        async with self._connect_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=self._config.timeout,
                    headers={
                        "X-API-KEY": self._config.api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        # Derive the User-Agent from the package version so it
                        # tracks releases automatically instead of drifting
                        # out of date as a hardcoded literal.
                        "User-Agent": f"greymatter-mcp/{__version__}",
                    },
                )

    async def close(self) -> None:
        """Close the connection pool and reset to the disconnected state.

        Safe to call when never connected (no-op). After closing, ``connect``
        can rebuild the client, so an instance is reusable.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self, customer_slug: str | None) -> dict[str, str]:
        """Build the per-request OpCo-targeting header.

        Args:
            customer_slug: An explicit OpCo slug for this call, or ``None`` to
                fall back to the default slug from config.

        Returns:
            A dict containing the ``x-reliaquest-customer`` header, or an empty
            dict when no slug is configured at all (single-OpCo accounts) — in
            which case the request is sent without the header.
        """
        # Per-call override wins; otherwise use the configured default.
        slug = customer_slug or self._config.customer_slug
        return {"x-reliaquest-customer": slug} if slug else {}

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        customer_slug: str | None = None,
        retryable: bool = True,
    ) -> Any:
        """Run a GraphQL document and return its ``data`` object.

        This is the one method every tool ultimately calls. It POSTs the
        standard GraphQL envelope ``{query, variables}`` and then unwraps the
        response down to the ``data`` payload that callers actually want.

        Args:
            query: The GraphQL document text (a query or mutation).
            variables: Variable values for the document; ``None`` is sent as an
                empty object, which GraphQL accepts.
            customer_slug: Optional OpCo slug to scope this single call to one
                company, overriding the configured default. Keyword-only to
                keep call sites self-documenting.
            retryable: When True (the default), transient network errors and
                ``429``/``5xx`` responses are retried with backoff. Callers MUST
                pass ``False`` for non-idempotent operations (mutations): if a
                mutation succeeds server-side but its response is lost, a retry
                would execute it a second time. With ``retryable=False`` the
                operation is sent exactly once and any transient failure is
                surfaced immediately instead of being retried.

        Returns:
            The ``data`` object from a successful GraphQL response (or, in the
            unusual case of a non-dict JSON body, the parsed body as-is).

        Raises:
            GreyMatterGraphQLError: When the response body carries a GraphQL
                ``errors`` array. This is the key GraphQL nuance: GraphQL
                routinely returns HTTP ``200`` even when the operation failed,
                signalling the failure *in the body* rather than the status
                line — which is exactly WHY we always parse and inspect the
                body instead of trusting the status code alone.
            GreyMatterAPIError: On HTTP ``>= 400`` responses, on a network
                failure that exhausts all retries, or on an undecodable
                (non-JSON) body.

        Transient failures (network errors and retryable ``429``/``5xx``
        statuses) are retried up to ``_MAX_RETRIES`` times using exponential
        backoff with *full jitter* (a random wait in ``[0, 2**attempt)``).
        Jitter spreads out concurrent retriers so a fleet of clients doesn't
        synchronize into a thundering herd hammering a recovering server. A
        server-provided ``Retry-After`` takes precedence over the computed
        backoff, but is capped at ``_MAX_RETRY_AFTER_SECONDS``.
        """
        # Lazily connect on first use so callers never have to remember to.
        if self._client is None:
            await self.connect()
        assert self._client is not None  # for type-checkers: connect() set it

        payload = {"query": query, "variables": variables or {}}
        headers = self._headers(customer_slug)

        # When set, holds the number of seconds to sleep *before* the next
        # attempt. None on the very first attempt means "send immediately".
        next_backoff: float | None = None
        for attempt in range(_MAX_RETRIES):
            # Wait out the backoff decided by the previous iteration, then clear
            # it so a successful path doesn't accidentally sleep again.
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
                # Network-level failure (DNS, connect, read timeout, etc.). On
                # the last attempt — or when the caller forbade retries (a
                # non-idempotent mutation) — give up with status 0 ("no HTTP
                # response"); otherwise schedule a jittered retry.
                if not retryable or attempt == _MAX_RETRIES - 1:
                    raise GreyMatterAPIError(0, f"Network error: {e}") from e
                logger.warning("Network error on attempt %d: %s", attempt + 1, e)
                next_backoff = random.uniform(0, 2**attempt)
                continue

            # Retryable status AND retries are allowed AND we still have attempts
            # left: prefer the server's Retry-After (capped) over our own jittered
            # backoff, then loop to try again. When retries are forbidden (a
            # mutation), a 429/5xx falls through to the hard-failure branch below
            # on the first attempt so the operation is never re-sent.
            if (
                retryable
                and response.status_code in _RETRYABLE_STATUS_CODES
                and attempt < _MAX_RETRIES - 1
            ):
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                next_backoff = (
                    min(retry_after, _MAX_RETRY_AFTER_SECONDS)
                    if retry_after is not None
                    else random.uniform(0, 2**attempt)
                )
                logger.warning("HTTP %d — will retry", response.status_code)
                continue

            # Any other 4xx/5xx (including a retryable status on the final
            # attempt) is a hard failure. Try to extract a human-friendly
            # message from a JSON error body, but fall back to raw text.
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

            # HTTP succeeded — but a GraphQL response is only as good as its
            # body, so decode it. A 200 with a non-JSON body is itself an error.
            try:
                parsed = response.json()
            except ValueError as e:
                raise GreyMatterAPIError(
                    response.status_code, f"Non-JSON response: {e}", response.text
                ) from e

            # The GraphQL nuance in action: even on HTTP 200 the body may carry
            # an `errors` array describing field-level failures. Surface those
            # (along with any partial `data`) rather than silently returning.
            errors = parsed.get("errors") if isinstance(parsed, dict) else None
            if errors:
                raise GreyMatterGraphQLError(errors, data=parsed.get("data"))
            # Success: hand back just the `data` payload callers care about.
            return parsed.get("data") if isinstance(parsed, dict) else parsed

        # Unreachable in practice: the loop always either returns or raises on
        # its final iteration. Kept as a defensive guard / for type narrowing.
        raise GreyMatterAPIError(0, "Max retries exceeded")  # pragma: no cover


# Process-wide singleton client plus a lock guarding its creation/teardown.
# Sharing one client (and its connection pool) across every tool call avoids
# the overhead and connection churn of building a fresh pool per request.
_client: GreyMatterClient | None = None
_client_lock = asyncio.Lock()


async def get_client() -> GreyMatterClient:
    """Return the process-wide shared client, creating it on first call.

    The lock makes lazy initialization safe under concurrency so that two
    coroutines requesting the client at once still end up sharing a single
    connected instance (and a single connection pool).

    Returns:
        A connected :class:`GreyMatterClient` ready to ``execute`` queries.
    """
    global _client
    async with _client_lock:
        if _client is None:
            _client = GreyMatterClient()
            await _client.connect()
    return _client


async def shutdown_client() -> None:
    """Close and discard the shared client, releasing its connection pool.

    Called once at server shutdown (see ``server.main``). Safe to call when no
    client was ever created. Resetting to ``None`` means a later ``get_client``
    can transparently rebuild one.
    """
    global _client
    async with _client_lock:
        if _client is not None:
            await _client.close()
            _client = None
