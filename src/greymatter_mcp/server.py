"""GreyMatter MCP server — entrypoint.

This is the process entrypoint that wires everything together into a runnable
Model Context Protocol (MCP) server exposing the ReliaQuest GreyMatter GraphQL
API to AI assistants. It is intentionally small: the heavy lifting lives in
sibling modules.

- :func:`build_server` constructs and configures a :class:`FastMCP` instance,
  validating configuration early and registering every tool.
- :func:`main` is the CLI: it parses transport arguments, builds the server,
  runs it, and best-effort cleans up the shared HTTP client on exit.
"""

from __future__ import annotations

import argparse
import logging
import sys

from fastmcp import FastMCP

from .client import shutdown_client
from .config import ConfigError, get_config
from .tools import register_all


def build_server() -> FastMCP:
    """Construct, configure, and fully populate the FastMCP server.

    Returns:
        A :class:`FastMCP` instance with logging configured and all GreyMatter
        tools registered, ready to be ``run``.

    Raises:
        ConfigError: Propagated from ``get_config()`` if required environment
            settings (e.g. the API key) are missing or invalid. We call config
            *first*, before any other setup, so misconfiguration fails fast and
            loudly instead of partway through startup.
    """
    config = get_config()  # validates env early — fail fast on bad config

    # Logging MUST go to stderr, never stdout. Under the default ``stdio``
    # transport the MCP protocol uses stdout as its message channel, so any
    # stray log line written there would corrupt the JSON-RPC stream and break
    # the connection with the client.
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdio transport owns stdout
    )

    # The `instructions` string is surfaced to the connected assistant as a
    # natural-language description of what this server offers and how to use it
    # (tool grouping, the graphql_query escape hatch, OpCo targeting, the
    # rate_limit budget tool, and read-only mode behavior).
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
    # Discover and register every MCP tool (the generated domain tools plus the
    # generic graphql_query escape hatch). Done last so the server is complete.
    register_all(mcp)
    return mcp


def main() -> int:
    """CLI entrypoint: parse arguments, run the server, and clean up.

    Supports two transports via ``--transport``: ``stdio`` (the default, used
    when an assistant launches the server as a subprocess) and ``http`` (a
    standalone HTTP server, where ``--host``/``--port`` — or their config
    defaults — apply).

    Returns:
        A process exit code: ``2`` if configuration is invalid, otherwise ``0``
        after the server has run and shut down.
    """
    parser = argparse.ArgumentParser(prog="greymatter-mcp")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    # Surface configuration problems as a clean error + exit code 2 rather than
    # an unhandled traceback, so launchers can distinguish "misconfigured" from
    # a genuine crash.
    try:
        mcp = build_server()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    config = get_config()  # cached singleton; reused here for host/port defaults
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            # CLI flags win when provided; otherwise fall back to config.
            mcp.run(
                transport="http",
                host=args.host or config.http_host,
                port=args.port or config.http_port,
            )
    finally:
        # Best-effort teardown of the shared HTTP client's connection pool.
        # Imported locally to keep the module import light and because this is
        # the only place it's needed.
        import asyncio

        # FastMCP's own event loop has already closed by the time we get here,
        # so we spin up a fresh one with asyncio.run. The httpx client being
        # closed was created on that now-gone loop, and aclose() can raise more
        # than RuntimeError (e.g. anyio errors) when run from a fresh loop, so we
        # swallow anything — cleanup is best-effort and the process is exiting.
        try:
            asyncio.run(shutdown_client())
        except Exception:  # noqa: BLE001 — best-effort cleanup; process is exiting
            pass
    return 0


if __name__ == "__main__":
    # Translate the integer return code into the process exit status.
    raise SystemExit(main())
