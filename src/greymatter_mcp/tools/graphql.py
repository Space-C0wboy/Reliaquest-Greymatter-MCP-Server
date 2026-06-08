"""Generic GraphQL escape-hatch tool."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from ._common import execute_operation


def is_mutation_document(query: str) -> bool:
    """True if the document contains a mutation operation.

    Robust against leading BOM, comments, and fragment definitions (a valid
    GraphQL document may define fragments before the operation). Errs toward
    classifying as a mutation so read-only mode cannot be bypassed.
    """
    # Strip a leading UTF-8 BOM and all line comments.
    text = query.lstrip("﻿")
    text = re.sub(r"#[^\n]*", "", text)
    text = text.strip()

    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] == "{":
            # Anonymous operation shorthand is a query.
            return False
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if not m:
            i += 1
            continue
        word = m.group(0)
        if word == "mutation":
            return True
        if word in ("query", "subscription"):
            return False
        if word == "fragment":
            brace = text.find("{", i)
            if brace == -1:
                break
            depth, j = 0, brace
            while j < n:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j
            continue
        i += len(word)

    # Couldn't classify a leading operation — be conservative: if the document
    # mentions a mutation keyword anywhere, treat it as a mutation.
    return bool(re.search(r"\bmutation\b", text))


def register(mcp: FastMCP, *, read_only: bool) -> None:
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
        if read_only and is_mutation_document(query):
            raise ValueError(
                "Server is in read-only mode (GREYMATTER_READ_ONLY); mutations are disabled."
            )
        return await execute_operation(query, variables, customer_slug=customer_slug)
