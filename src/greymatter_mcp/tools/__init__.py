"""GreyMatter MCP tool registry."""

from __future__ import annotations

from fastmcp import FastMCP

from ..config import get_config
from . import graphql
from ._generated import GENERATED_MODULES


def register_all(mcp: FastMCP) -> None:
    """Register every tool. Mutation tools are skipped when read-only is set."""
    read_only = get_config().read_only
    for module in GENERATED_MODULES:
        module.register(mcp, read_only=read_only)
    graphql.register(mcp, read_only=read_only)
