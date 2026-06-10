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
import re
from typing import Any

from ..client import get_client


def is_mutation_document(query: str) -> bool:
    """Return True if the GraphQL document's operation is a mutation.

    Args:
        query: A raw GraphQL document string.

    Returns:
        True if the leading (or, as a fallback, any) operation is a mutation.

    This is a lightweight, hand-rolled scanner rather than a full GraphQL parser.
    It is deliberately robust against the things that trip up naive checks — a
    leading UTF-8 BOM, ``#`` line comments, and ``fragment`` definitions that a
    valid document may place before its operation. Crucially it scans *every*
    operation in the document, not just the leading one: a document like
    ``query a { x } mutation b { y }`` is a mutation, and stopping at the first
    ``query`` keyword would let a mutation ride along behind a read and defeat
    read-only mode on a lenient server. It also errs toward classifying a
    document as a mutation: in read-only mode a false "mutation" only blocks a
    read (annoying but safe), whereas a missed mutation would defeat the safety
    switch entirely.

    It is hosted here (rather than in ``graphql.py``) so that ``execute_operation``
    can consult it to decide whether an operation is safe to retry — mutations are
    not idempotent and must be sent exactly once.

    String literals are handled explicitly: a ``{``, ``}``, or the word ``mutation``
    *inside* a GraphQL string value (e.g. ``query { f(q: "} mutation") { id } }``)
    must not affect brace depth or be read as a keyword, or a harmless read would be
    misclassified as a mutation and wrongly rejected in read-only mode.
    """
    # Drop a leading UTF-8 BOM (some editors/clients prepend one) and strip every
    # "#..." line comment so commented-out keywords can't fool the scan.
    text = query.lstrip("﻿")
    text = re.sub(r"#[^\n]*", "", text)
    text = text.strip()
    n = len(text)

    def skip_string(start: int) -> int:
        """Return the index just past the string literal that begins at ``start``.

        ``start`` must point at a ``"``. Handles both block strings (``\"\"\"...\"\"\"``)
        and ordinary strings (with ``\\`` escapes). Used to step over string values so
        their contents are never parsed as document structure.
        """
        if text[start : start + 3] == '"""':
            end = text.find('"""', start + 3)
            return end + 3 if end != -1 else n
        j = start + 1
        while j < n:
            if text[j] == "\\":  # backslash escapes the next char (e.g. \")
                j += 2
                continue
            if text[j] == '"':
                return j + 1
            j += 1
        return n

    def skip_braced_block(start: int) -> int:
        """Return the index just past the {...} block at/after start, or -1.

        Skips string literals while both locating the opening brace and matching
        depth, so braces inside a string value can't end the block prematurely.
        """
        # Locate the opening brace, stepping over any string literal in the way
        # (e.g. a variable default value like `= "{"`).
        j = start
        while j < n and text[j] != "{":
            if text[j] == '"':
                j = skip_string(j)
                continue
            j += 1
        if j >= n:
            return -1
        depth = 0
        while j < n:
            c = text[j]
            if c == '"':
                j = skip_string(j)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return -1

    i = 0
    parse_failed = False
    while i < n:
        # Whitespace and commas are insignificant separators in GraphQL.
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] == '"':
            # A string literal at the top level (e.g. a variable default value);
            # step over it so its contents can't be mistaken for structure.
            i = skip_string(i)
            continue
        if text[i] == "{":
            # Anonymous query shorthand — a query; skip its body, keep scanning.
            nxt = skip_braced_block(i)
            if nxt == -1:
                parse_failed = True
                break
            i = nxt
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if not m:
            i += 1
            continue
        word = m.group(0)
        if word == "mutation":
            return True
        if word in ("query", "subscription", "fragment"):
            # A non-mutation definition: skip its entire body and KEEP
            # scanning — a mutation may legally follow in the same document.
            nxt = skip_braced_block(i)
            if nxt == -1:
                parse_failed = True
                break
            i = nxt
            continue
        i += len(word)

    if parse_failed:
        # Couldn't scan structurally — be conservative: any "mutation" word
        # anywhere means we treat the document as a mutation.
        return bool(re.search(r"\bmutation\b", text))
    return False


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
    # Only queries are safe to retry. A mutation that succeeds server-side but
    # whose response is lost (read timeout, gateway 5xx) would be re-sent on a
    # retry and run twice — duplicate comments, duplicate API keys, a playbook
    # run twice. Mutations are not idempotent, so they go out exactly once.
    return await client.execute(
        query,
        cleaned,
        customer_slug=customer_slug,
        retryable=not is_mutation_document(query),
    )
