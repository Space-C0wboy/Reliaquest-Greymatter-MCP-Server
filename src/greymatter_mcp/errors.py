"""Exception types raised by the GreyMatter GraphQL client.

These two exceptions let callers distinguish *where* a request went wrong, which
matters because the two failure modes look very different at the HTTP layer:

- ``GreyMatterAPIError`` — the request never produced a usable GraphQL response.
  This covers transport failures (DNS, timeout, connection reset) and any non-2xx
  HTTP status (401 auth, 429 rate limit, 5xx server error, etc.).
- ``GreyMatterGraphQLError`` — the HTTP call *succeeded* (200 OK) but the GraphQL
  operation itself failed and the response body carried an ``errors`` array.

Keeping them separate means tool code can, for example, retry/back off on a
transport error but surface a GraphQL validation error straight to the user.
"""

from __future__ import annotations

from typing import Any


class GreyMatterAPIError(RuntimeError):
    """Transport-level or non-2xx HTTP failure talking to the GreyMatter API.

    Raised when there is no valid GraphQL response to parse — e.g. the connection
    failed, or the server returned a status code outside 2xx. The attributes carry
    enough context to log or display the failure and to branch on the status code
    (e.g. treat 429 as rate-limited).

    Args:
        status_code: The HTTP status returned by the server (or a synthetic code
            chosen by the caller when no real response was received).
        message: Human-readable description of what went wrong.
        body: The raw response body, when available, for debugging/logging.
    """

    def __init__(self, status_code: int, message: str, body: Any = None):
        # Compose a single readable summary for the base RuntimeError message so
        # that str(exc) is useful even when nobody inspects the attributes.
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code  # numeric HTTP status, e.g. 401, 429, 503
        self.message = message  # short description of the failure
        self.body = body  # raw response payload, if any, for diagnostics


class GreyMatterGraphQLError(RuntimeError):
    """Raised when a GraphQL response carries a non-empty ``errors`` array.

    GraphQL returns HTTP 200 even for operation-level errors (bad field, failed
    validation, resolver exception), so a successful HTTP call can still represent
    a failed operation. That is *why* this is a separate type from
    ``GreyMatterAPIError`` — the transport was fine, but the operation was not.

    Args:
        errors: The ``errors`` array from the GraphQL response. Each entry is a
            dict that conventionally has a ``message`` key (and possibly more).
        data: The partial ``data`` payload, if the server returned any alongside
            the errors (GraphQL permits partial results).
    """

    def __init__(self, errors: list[dict[str, Any]], data: Any = None):
        # Flatten every error's "message" into one semicolon-joined string. Fall
        # back to str(e) if an entry lacks "message", and to a generic label if
        # the list somehow yields no text at all.
        messages = "; ".join(str(e.get("message", e)) for e in errors) or "unknown GraphQL error"
        super().__init__(f"GraphQL error: {messages}")
        self.errors = errors  # full list of GraphQL error objects, preserved as-is
        self.data = data  # any partial data the server returned with the errors
