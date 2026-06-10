"""The generic ``graphql_query`` escape-hatch tool.

Not every GreyMatter operation has a dedicated generated tool. This module
provides one catch-all tool that runs an arbitrary GraphQL document, so an AI
assistant can reach any part of the API. Because that bypasses the per-tool
read-only filtering, it also contains ``is_mutation_document`` — a defensive
parser that decides whether a raw document is a mutation, so read-only mode can
reject mutations submitted through this back door.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

# ``is_mutation_document`` lives in ``_common`` so the shared executor can use it
# to decide retry-safety; it is re-exported here because this module (and its
# tests) is its original home and read-only enforcement consults it directly.
from ._common import execute_operation, is_mutation_document

__all__ = ["is_mutation_document", "register"]


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
