"""Shared helpers for generated GreyMatter tools."""

from __future__ import annotations

import json
from typing import Any

from ..client import get_client


def drop_none(variables: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is None so optional GraphQL variables are omitted."""
    return {k: v for k, v in variables.items() if v is not None}


def coerce_json(value: Any) -> Any:
    """Parse a JSON string that encodes an object or array back into Python.

    Many GraphQL variables are input objects (filters, orders) or lists. MCP
    clients sometimes serialize such complex tool arguments as a JSON *string*
    (the generated params are loosely typed), but the GraphQL endpoint requires
    real objects/arrays ("Expected type 'Map' but was 'String'"). This recovers
    them. Plain scalar strings (cursors, ids) don't start with `{`/`[`, so they
    pass through untouched; anything that fails to parse is left as-is.
    """
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped[:1] in ("{", "["):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                return value
            if isinstance(parsed, (dict, list)):
                return parsed
    return value


async def execute_operation(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    customer_slug: str | None = None,
) -> Any:
    """Run a GraphQL document via the shared client.

    None variables are omitted, and JSON-string object/array arguments are
    coerced back into real objects/arrays.
    """
    client = await get_client()
    cleaned = {k: coerce_json(v) for k, v in drop_none(variables or {}).items()}
    return await client.execute(query, cleaned, customer_slug=customer_slug)
