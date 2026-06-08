"""Generic GraphQL escape-hatch tool."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from ._common import execute_operation

# Strip leading whitespace and full-line comments, then read the first keyword.
_LEADING = re.compile(r"^\s*(?:#[^\n]*\n\s*)*")


def is_mutation_document(query: str) -> bool:
    """True if the document's first operation is a mutation."""
    stripped = _LEADING.sub("", query)
    return stripped.lstrip().lower().startswith("mutation")


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
