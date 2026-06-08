# Changelog

## [0.1.1] - 2026-06-08
### Fixed
- Coerce JSON-string object/array arguments back into real objects before sending
  to GraphQL. MCP clients may serialize complex tool arguments (filters, orders,
  input objects) as JSON strings, which the API rejected with
  *"Expected type 'Map' but was 'String'"*. Affected all tools taking input-object
  or list variables (e.g. `incidents` with `incidentFilter`/`incidentOrder`).

## [0.1.0] - 2026-06-08
### Added
- Initial release of the ReliaQuest GreyMatter MCP server.
- 146 curated GraphQL tools across 22 domains (incidents, tasks, detections, playbooks, cases, DRP alerts, access groups, users, assets, and more), generated from the vendor Postman collection.
- Generic `graphql_query` escape-hatch tool for operations without a dedicated tool.
- Read-only mode (`GREYMATTER_READ_ONLY`) that hides all mutation tools.
- Multi-OpCo support via the `x-reliaquest-customer` header (`GREYMATTER_CUSTOMER_SLUG` / per-call `customer_slug`).
- Async GraphQL client with retry/backoff and GraphQL-error handling.
- Collection-driven tool generator and live-schema introspection script.
- stdio and HTTP transports.
