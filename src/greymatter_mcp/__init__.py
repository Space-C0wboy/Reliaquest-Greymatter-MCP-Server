"""Top-level package for the ReliaQuest GreyMatter MCP server.

This package implements a Model Context Protocol (MCP) server that exposes the
ReliaQuest GreyMatter GraphQL API to AI assistants (for example, Claude). MCP is
the protocol an assistant uses to discover and call external "tools"; this server
turns each GreyMatter GraphQL operation into such a tool so an assistant can query
incidents, tasks, detections, cases, DRP alerts, and more without speaking GraphQL
directly.

Subpackage/module roles:
- ``config``: reads environment-driven settings into a frozen ``Config`` object.
- ``errors``: the two exception types the GraphQL client can raise.
- ``client`` (owned elsewhere): the HTTP/GraphQL transport.
- ``tools``: the MCP tool registry — generated domain tools plus the generic
  ``graphql_query`` escape hatch.

This module itself is just the package marker; its only job is to declare the
package version, which is reported to MCP clients during the handshake.
"""

# Single source of truth for the package version. Surfaced to MCP clients on
# connect and kept in sync with the version recorded in the project metadata.
__version__ = "0.1.2"
