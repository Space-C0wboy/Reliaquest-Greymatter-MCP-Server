"""Tool registry for the GreyMatter MCP server.

This module is the single entry point that wires every callable tool into the
FastMCP server. It pulls together two sources of tools:

1. ``GENERATED_MODULES`` — one module per GreyMatter API domain (incidents, tasks,
   detections, cases, DRP alerts, etc.), generated from the GraphQL schema. Each
   exposes a ``register(mcp, read_only=...)`` function that adds its tools.
2. ``graphql`` — the generic ``graphql_query`` escape hatch for operations that
   don't have a dedicated generated tool.

The server's startup code calls ``register_all`` once; after that, the MCP client
can discover and invoke whatever tools were registered.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..config import get_config
from . import graphql
from ._generated import GENERATED_MODULES


def register_all(mcp: FastMCP) -> None:
    """Register every available tool on the given FastMCP server.

    Args:
        mcp: The FastMCP server instance to attach tools to.

    Behavior:
        Reads ``read_only`` from the global config and passes it down to each
        module's ``register``. In read-only mode the generated modules skip their
        mutation tools (so they never appear to the client) and ``graphql_query``
        rejects mutation documents at call time. This is the central place that
        enforces the read-only safety switch across all tools.
    """
    # One config read up front; the same flag governs every module below.
    read_only = get_config().read_only
    # Register each generated domain module's tools, honoring read-only mode.
    for module in GENERATED_MODULES:
        module.register(mcp, read_only=read_only)
    # Finally add the generic escape-hatch tool, which also respects read-only.
    graphql.register(mcp, read_only=read_only)
