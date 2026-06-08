# Changelog

## [0.1.3] - 2026-06-08
### Changed
- Extensive teaching-style code documentation across the codebase (module/function
  docstrings + inline comments), including comments emitted into the generated tool
  modules. No behavior change.
- `User-Agent` header now derives from the package `__version__` instead of a hardcoded
  string.

## [0.1.2] - 2026-06-08
### Fixed
- Generator now prunes orphaned GraphQL variable declarations after a field/selection is
  stripped, fixing an `UnusedVariable` validation error that broke the `case` tool (#3).
### Changed
- Trim heavy mutation response selection sets (`retain_incident`, `release_incident`,
  `unresolve_incident`, `update_task_retained_status`) to a minimal confirmation to reduce
  payload and client-timeout risk (#1).
- Raise the default `GREYMATTER_TIMEOUT` from 30s to 60s — some mutations are slow
  server-side; the old default caused a wasteful retry before succeeding (#1).
- `create_case` tool description now notes that `state` is effectively required (the API
  returns `success=false` with no error if omitted) (#2).
### Notes
- Documented the single-item-getter "access denied" vendor behavior in
  `docs/reliaquest-api-issues.md` (#4).

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
