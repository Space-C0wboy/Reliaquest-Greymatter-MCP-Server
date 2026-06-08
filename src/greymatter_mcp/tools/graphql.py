"""The generic ``graphql_query`` escape-hatch tool.

Not every GreyMatter operation has a dedicated generated tool. This module
provides one catch-all tool that runs an arbitrary GraphQL document, so an AI
assistant can reach any part of the API. Because that bypasses the per-tool
read-only filtering, it also contains ``is_mutation_document`` — a defensive
parser that decides whether a raw document is a mutation, so read-only mode can
reject mutations submitted through this back door.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from ._common import execute_operation


def is_mutation_document(query: str) -> bool:
    """Return True if the GraphQL document's operation is a mutation.

    Args:
        query: A raw GraphQL document string.

    Returns:
        True if the leading (or, as a fallback, any) operation is a mutation.

    This is a lightweight, hand-rolled scanner rather than a full GraphQL parser.
    It is deliberately robust against the things that trip up naive checks — a
    leading UTF-8 BOM, ``#`` line comments, and ``fragment`` definitions that a
    valid document may place before its operation. It also errs toward classifying
    a document as a mutation: in read-only mode a false "mutation" only blocks a
    read (annoying but safe), whereas a missed mutation would defeat the safety
    switch entirely.
    """
    # Drop a leading UTF-8 BOM (some editors/clients prepend one) and strip every
    # "#..." line comment so commented-out keywords can't fool the scan.
    text = query.lstrip("﻿")
    text = re.sub(r"#[^\n]*", "", text)
    text = text.strip()

    # Walk the document token by token looking for the first operation keyword.
    i, n = 0, len(text)
    while i < n:
        # Skip insignificant characters: GraphQL treats whitespace and commas as
        # ignorable separators between tokens.
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] == "{":
            # A bare "{" with no preceding keyword is the anonymous query
            # shorthand, which is always a query.
            return False
        # Try to read a GraphQL name (keyword or operation name) at the cursor.
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if not m:
            # Not a name (e.g. a stray punctuation char) — step over it.
            i += 1
            continue
        word = m.group(0)
        if word == "mutation":
            return True
        if word in ("query", "subscription"):
            # An explicit non-mutation operation leads the document.
            return False
        if word == "fragment":
            # A fragment definition precedes the operation. Skip its entire body
            # by brace-matching so we don't mistake names inside it for the
            # operation keyword.
            brace = text.find("{", i)
            if brace == -1:
                # Malformed (no body) — give up the structured scan.
                break
            depth, j = 0, brace
            while j < n:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        # Found the matching close brace; resume just past it.
                        j += 1
                        break
                j += 1
            i = j
            continue
        # Some other leading name we don't recognize as an operation keyword;
        # advance past it and keep scanning.
        i += len(word)

    # Structured scan didn't find a leading operation keyword. Be conservative:
    # if the word "mutation" appears anywhere in the document, treat it as one so
    # read-only mode can't be bypassed by an unusual document layout.
    return bool(re.search(r"\bmutation\b", text))


def register(mcp: FastMCP, *, read_only: bool) -> None:
    """Register the ``graphql_query`` tool on the FastMCP server.

    Args:
        mcp: The FastMCP server to attach the tool to.
        read_only: When True, the tool refuses mutation documents at call time
            (it is still registered so read operations remain available).
    """

    @mcp.tool(
        name="graphql_query",
        description=(
            "Run an arbitrary GraphQL document against the GreyMatter API. Use this "
            "for operations not covered by a dedicated tool. Provide the full query/"
            "mutation string and an optional variables object. When the server is in "
            "read-only mode, mutation documents are rejected."
        ),
    )
    async def graphql_query(
        query: Annotated[str, Field(description="The full GraphQL query or mutation document.")],
        variables: Annotated[
            dict | None,
            Field(default=None, description="Variables object for the document."),
        ] = None,
        customer_slug: Annotated[
            str | None,
            Field(default=None, description="Override the x-reliaquest-customer (OpCo) header."),
        ] = None,
    ) -> Any:
        """Execute the caller-supplied GraphQL document and return its data.

        Args:
            query: The full GraphQL document to run.
            variables: Optional variables object for the document.
            customer_slug: Optional OpCo override for the x-reliaquest-customer
                header on multi-OpCo accounts.

        Returns:
            The operation's ``data`` payload.

        Raises:
            ValueError: if the server is read-only and ``query`` is detected as a
                mutation — checked here, before any request is sent.
        """
        # Enforce the read-only safety switch for the escape hatch. The detection
        # is intentionally conservative (see is_mutation_document).
        if read_only and is_mutation_document(query):
            raise ValueError(
                "Server is in read-only mode (GREYMATTER_READ_ONLY); mutations are disabled."
            )
        # Delegate to the shared executor, which normalizes variables and runs the
        # document via the shared client.
        return await execute_operation(query, variables, customer_slug=customer_slug)
