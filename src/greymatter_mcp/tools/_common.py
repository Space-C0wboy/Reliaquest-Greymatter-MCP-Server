"""Shared helpers for generated GreyMatter tools."""

from __future__ import annotations

from typing import Any

from ..client import get_client


def drop_none(variables: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is None so optional GraphQL variables are omitted."""
    return {k: v for k, v in variables.items() if v is not None}


async def execute_operation(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    customer_slug: str | None = None,
) -> Any:
    """Run a GraphQL document via the shared client, omitting None variables."""
    client = await get_client()
    return await client.execute(
        query, drop_none(variables or {}), customer_slug=customer_slug
    )
