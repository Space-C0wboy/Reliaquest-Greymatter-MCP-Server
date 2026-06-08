"""Shared helpers used by every generated GreyMatter tool.

The generated domain tools (incidents, tasks, etc.) are thin wrappers: each
collects its arguments and then hands a GraphQL document plus variables to this
module to actually run. Centralizing that here keeps the generated code small and
puts the two argument-normalization rules MCP requires in one place:

- ``drop_none``  — don't send variables the caller left unset.
- ``coerce_json`` — repair complex arguments that an MCP client serialized as a
  JSON string instead of a real object/array.

``execute_operation`` ties both together and dispatches via the shared client.
"""

from __future__ import annotations

import json
from typing import Any

from ..client import get_client


def drop_none(variables: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``variables`` with all ``None`` values removed.

    Args:
        variables: The raw variables dict, where optional/unset arguments arrive
            as ``None``.

    Returns:
        A new dict containing only the keys whose value is not ``None``.

    Why: GraphQL distinguishes "argument omitted" from "argument explicitly null".
    Sending ``None`` for an optional variable can trigger validation errors or
    overwrite a value with null, so unset arguments must be dropped entirely.
    """
    return {k: v for k, v in variables.items() if v is not None}


def coerce_json(value: Any) -> Any:
    """Parse a JSON string that encodes an object or array back into Python.

    Many GraphQL variables are input objects (filters, orders) or lists. MCP
    clients sometimes serialize such complex tool arguments as a JSON *string*
    (the generated params are loosely typed), but the GraphQL endpoint requires
    real objects/arrays ("Expected type 'Map' but was 'String'"). This recovers
    them. Plain scalar strings (cursors, ids) don't start with `{`/`[`, so they
    pass through untouched; anything that fails to parse is left as-is.

    Args:
        value: A single variable value of any type.

    Returns:
        The parsed object/array if ``value`` was a JSON string encoding one;
        otherwise ``value`` unchanged.
    """
    # Only strings are candidates for repair; everything else is already typed.
    if isinstance(value, str):
        # Look at the first non-whitespace char to cheaply decide whether this
        # could be a JSON object/array before attempting a full parse.
        stripped = value.lstrip()
        if stripped[:1] in ("{", "["):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                # Looked like JSON but wasn't valid — leave the original string
                # untouched and let the API report a meaningful error if needed.
                return value
            # Guard against edge cases like a quoted scalar; only swap in the
            # parsed result when it really is a container type.
            if isinstance(parsed, (dict, list)):
                return parsed
    return value


async def execute_operation(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    customer_slug: str | None = None,
) -> Any:
    """Run a GraphQL document through the shared client, normalizing variables.

    Args:
        query: The GraphQL query or mutation document to execute.
        variables: Optional variables for the document. ``None`` is treated as an
            empty mapping.
        customer_slug: Optional override for the x-reliaquest-customer (OpCo)
            header, to target a specific company on multi-OpCo accounts.

    Returns:
        The ``data`` payload returned by the client for the operation.

    The two normalization steps mirror the helpers above: first ``drop_none``
    removes unset variables, then ``coerce_json`` repairs any that arrived as JSON
    strings — so the API always receives clean, correctly typed variables.
    """
    # Reuse the process-wide client (handles auth, base URL, and timeouts).
    client = await get_client()
    # Drop unset vars first, then coerce the survivors so we never waste effort
    # parsing values that were going to be discarded anyway.
    cleaned = {k: coerce_json(v) for k, v in drop_none(variables or {}).items()}
    return await client.execute(query, cleaned, customer_slug=customer_slug)
