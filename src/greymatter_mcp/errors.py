"""Exception types for the GreyMatter client."""

from __future__ import annotations

from typing import Any


class GreyMatterAPIError(RuntimeError):
    """Raised on transport failures or non-2xx HTTP responses."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class GreyMatterGraphQLError(RuntimeError):
    """Raised when a GraphQL response carries a non-empty `errors` array.

    GraphQL returns HTTP 200 even for operation-level errors, so this is
    distinct from the transport-level GreyMatterAPIError.
    """

    def __init__(self, errors: list[dict[str, Any]], data: Any = None):
        messages = "; ".join(str(e.get("message", e)) for e in errors) or "unknown GraphQL error"
        super().__init__(f"GraphQL error: {messages}")
        self.errors = errors
        self.data = data
