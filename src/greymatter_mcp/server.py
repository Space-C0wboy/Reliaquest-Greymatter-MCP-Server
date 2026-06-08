"""GreyMatter MCP server — entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys

from fastmcp import FastMCP

from .client import shutdown_client
from .config import ConfigError, get_config
from .tools import register_all


def build_server() -> FastMCP:
    config = get_config()  # validates env early

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdio transport owns stdout
    )

    mcp = FastMCP(
        name="greymatter-mcp",
        instructions=(
            "MCP server for the ReliaQuest GreyMatter GraphQL API. Tools are grouped "
            "by domain (incidents, tasks, detections, playbooks, cases, DRP alerts, "
            "etc.). Use `graphql_query` for anything without a dedicated tool. For "
            "multi-OpCo accounts, pass `customer_slug` to target a company. Check "
            "remaining API budget with the `rate_limit` tool. When the server runs "
            "with GREYMATTER_READ_ONLY=true, mutation tools are hidden and "
            "`graphql_query` rejects mutations."
        ),
    )
    register_all(mcp)
    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(prog="greymatter-mcp")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    try:
        mcp = build_server()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    config = get_config()
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(
                transport="http",
                host=args.host or config.http_host,
                port=args.port or config.http_port,
            )
    finally:
        import asyncio

        try:
            asyncio.run(shutdown_client())
        except RuntimeError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
