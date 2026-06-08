# ReliaQuest GreyMatter MCP Server — Design

**Date:** 2026-06-08
**Status:** Approved (pending final spec review)
**Author:** Kierston Grantham

## 1. Purpose

Build a Model Context Protocol (MCP) server that exposes the ReliaQuest
GreyMatter Self-Service API to AI tooling (Claude Desktop, etc.). It mirrors the
structure and conventions of the existing in-house MCP servers
([ThreatLocker-MCP](https://github.com/Space-C0wboy/ThreatLocker-MCP) and
[Checkpoint-Harmony-Email-MCP-Server](https://github.com/Space-C0wboy/Checkpoint-Harmony-Email-MCP-Server))
so that operators get a consistent experience and the codebase is familiar to
maintainers.

The key difference from those two servers: GreyMatter is a **single GraphQL
endpoint**, not a REST API. The architecture is adapted accordingly.

## 2. Background — the GreyMatter API

- **Endpoint:** `POST https://greymatter.myreliaquest.com/graphql` (single URL).
- **Protocol:** GraphQL. All requests are HTTP POST with a JSON body of
  `{"query": "...", "variables": {...}}`.
- **Auth:** header `X-API-KEY: <key>`. No bearer scheme; not email/password.
  Each user may hold exactly one key; keys expire (default 1 year) and cannot be
  renewed (must be recreated).
- **Multi-OpCo:** accounts managing multiple operating companies send an
  additional `x-reliaquest-customer` header (the "Header Slug") to target a
  specific company.
- **Introspection:** enabled — the schema can be queried directly.
- **Rate limiting:** 5000 points per company account per hour; each Node entity
  in a request counts as one point.
- **Pagination:** cursor-based (for syncing) and offset-based (for record
  retrieval). Connections follow the Relay pattern (`edges { cursor node }`,
  `pageInfo`, `totalCount`).
- **GraphQL error semantics:** a `200 OK` response can still contain an
  `errors` array; the client must inspect the body, not just the HTTP status.

### Documented capabilities (from reference PDFs + DataBee integration doc)

| Capability | Use case | Method |
|---|---|---|
| **Investigate** | List/get incidents, engineering (health) incidents, tasks; read comments; read customer users | Query |
| **Investigate** | Acknowledge, assign, comment, change state, close incidents; assign/comment/resolve tasks | Mutation |
| **Detect** | View deployed detection rules (with MITRE ATT&CK mapping) | Query |
| **Respond** | Run predefined playbooks; read playbook execution results | Mutation / Query |
| **Metrics** | Reporting queries for BI tools | Query |
| **API Key Management** | View/create/edit/delete API keys | Query / Mutation |
| **Assets** *(per DataBee)* | Devices, IPs, OS info | Query |

### Known operations (from the Jira/ServiceNow quick-start examples)

Queries: `incidents(incidentFilter, incidentOrder, after, first)`,
`incident(by: IncidentBy)`, `healthIncidents(incidentFilter:
HealthIncidentFilter, ...)`, `tasks(taskFilter, taskOrder, ...)`,
`task(by: TaskBy)`, incident/task `comments(filter, order, ...)`,
`customer { users }`.

Mutations: `acknowledgeIncident(input: IncidentAcknowledgementInput!)`,
`assignIncident(input: AssignIncidentInput!)`,
`addIncidentComment(input: IncidentCommentInput!)`,
`closeIncident(request: CloseIncidentRequest)`,
`updateIncidentState(input: UpdateIncidentStateInput!)`,
`assignTask(input: AssignTaskInput!)`,
`addTaskComment(input: TaskCommentInput!)`,
`resolveTask(input: ResolveTaskInput!)`.

Documented enums:
- Incident states include `PENDING_CUSTOMER`, `PENDING_RQ`, `RESOLVED`,
  `CANCELLED`.
- Incident close codes: `CUSTOMER_ANOMALOUS_SAFE`, `CUSTOMER_FALSE_POSITIVE`,
  `CUSTOMER_TRUE_POSITIVE`, `FALSE_POSITIVE_CREATE_TUNING_TICKET`,
  `CUSTOMER_SECURITY_CONTROL_TESTING`, `CUSTOMER_CANCELLED`.
- Task close codes: `CANCELLED`, `DUPLICATE`, `RESOLVED`.
- Comment types include `PUBLIC`.
- Acknowledgement method includes `WEB_UI`.

> Exact field names, additional enum members, and the schema for Detect /
> Respond / Metrics / API-Key / Assets capabilities will be confirmed from the
> exported Postman collection and live introspection before those tools are
> finalized (see §8).

## 3. Goals & non-goals

**Goals**
- Cover all documented capabilities: Investigate (full), Detect, Respond,
  Metrics, API Key Management (and Assets if present in the schema).
- Match the reference repos' layout, tooling, and conventions.
- Safe-by-option: a read-only toggle that hides all mutating tools.
- A generic GraphQL escape hatch for the long tail.

**Non-goals**
- Returning query-log results (Main Search / Targeted Query) — explicitly
  excluded by the GreyMatter API itself.
- Building new detection queries against client technology — out of API scope.
- A polished pydantic model for every response type up front; responses are
  returned as parsed JSON. Typed models may be added incrementally where they
  add value.

## 4. Architecture & approach

**Hybrid tool construction.** Unlike ThreatLocker (REST + OpenAPI codegen), the
GraphQL tools are **hand-curated** wrappers around named GraphQL documents, with
selection sets chosen by hand. They are validated against the introspected
schema and the exported Postman collection. This is the right fit for GraphQL,
where selection-set generation requires human judgment.

**Language & stack:** Python ≥3.10, [FastMCP](https://github.com/jlowin/fastmcp)
≥2.0, httpx, pydantic v2, python-dotenv — identical to the reference servers.

## 5. Project layout

```
greymatter-mcp/
├── .env.example
├── .gitignore
├── LICENSE                         # MIT
├── README.md
├── CHANGELOG.md
├── pyproject.toml                  # hatchling build, ruff, pytest
├── docs/
│   └── ENDPOINTS.md                # operation → tool catalog
├── scripts/
│   ├── introspect.py               # GraphQL introspection → schema/schema.graphql + schema.json
│   ├── run.ps1 / run.sh
│   └── setup.ps1 / setup.sh
├── schema/
│   └── schema.graphql              # introspected SDL (committed for reference)
├── src/greymatter_mcp/
│   ├── __init__.py
│   ├── config.py                   # env-based Config dataclass
│   ├── client.py                   # async GraphQL client (httpx)
│   ├── errors.py                   # GreyMatterAPIError, GreyMatterGraphQLError
│   ├── queries.py                  # centralized GraphQL document strings + selection sets
│   └── tools/
│       ├── __init__.py             # register_all(mcp) + read-only gating
│       ├── _common.py              # pagination/order args, shared serialization helpers
│       ├── incidents.py            # list/get/comments + mutations
│       ├── health_incidents.py     # engineering (RQ-EX) incidents
│       ├── tasks.py                # list/get/comments + mutations
│       ├── customer.py             # customer users
│       ├── detect.py               # detection rules (post-introspection)
│       ├── respond.py              # playbooks run/results (post-introspection)
│       ├── metrics.py              # metrics queries (post-introspection)
│       ├── api_keys.py             # API key mgmt (post-introspection)
│       ├── assets.py               # assets, if present in schema (post-introspection)
│       └── graphql.py              # generic graphql_query escape hatch
├── tests/                          # pytest + pytest-httpx, one file per tool module
└── .github/workflows/
    ├── ci.yml
    └── release.yml
```

## 6. Components

### 6.1 `config.py`
Env-based frozen `Config` dataclass with a lazy `get_config()` singleton and a
`ConfigError`, matching the reference pattern.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `GREYMATTER_API_KEY` | ✅ | — | `X-API-KEY` value |
| `GREYMATTER_BASE_URL` | | `https://greymatter.myreliaquest.com/graphql` | endpoint |
| `GREYMATTER_CUSTOMER_SLUG` | | — | default `x-reliaquest-customer` header (OpCo) |
| `GREYMATTER_READ_ONLY` | | `false` | when true, mutation tools are not registered |
| `GREYMATTER_TIMEOUT` | | `30` | request timeout (seconds) |
| `LOG_LEVEL` | | `INFO` | logging level |
| `MCP_HTTP_HOST` | | `127.0.0.1` | HTTP transport bind host |
| `MCP_HTTP_PORT` | | `8765` | HTTP transport bind port |

### 6.2 `client.py`
A process-wide shared async `GreyMatterClient`:
- `execute(query: str, variables: dict | None = None, *, customer_slug: str | None = None) -> Any`
  posts to the single endpoint and returns the `data` object.
- Sends `X-API-KEY`; adds `x-reliaquest-customer` when a slug is configured or
  passed per call.
- **GraphQL-aware error handling:** raises `GreyMatterGraphQLError` when the
  response body contains a non-empty `errors` array (even on HTTP 200); raises
  `GreyMatterAPIError` on non-2xx.
- Retry/backoff with full jitter on network errors, 429, and 5xx; honors
  `Retry-After` (capped). Logs rate-limit context.
- Lazy connect guarded by a lock; clean `shutdown_client()` on process exit.
  Same lifecycle shape as the ThreatLocker client.

### 6.3 `errors.py`
`GreyMatterAPIError` (HTTP/transport, carries status + body) and
`GreyMatterGraphQLError` (carries the GraphQL `errors` list).

### 6.4 `queries.py`
Centralized GraphQL document strings and reusable selection-set fragments so the
tool modules stay declarative and selection sets are maintained in one place.

### 6.5 `tools/`
Each module exposes `register(mcp, *, read_only: bool)`. `register_all(mcp)`
reads config and passes `read_only` through; mutation tools are simply not
registered when read-only is on. Every tool accepts an optional `customer_slug`
override parameter (analogous to ThreatLocker's `organization_id`). Documented
enums (states, close codes, comment types) are exposed as validated literals.

## 7. Tool inventory

**Queries (always registered):**
- `list_incidents` — filter (state, updated range, severity, etc.), order,
  pagination
- `get_incident` — by id or ticket number; includes comments, artifacts,
  metadata, rule, assignee
- `list_incident_comments`
- `list_health_incidents` / `get_health_incident` — engineering incidents
- `list_tasks` / `get_task` (with comments) / `list_task_comments`
- `list_customer_users` — resolve GreyMatter user IDs for assignment
- `graphql_query` — escape hatch; **query-only when read-only is set**
- Detect / Respond (read) / Metrics / Assets / API-key (read) query tools —
  finalized post-introspection

**Mutations (registered only when `GREYMATTER_READ_ONLY` is false):**
- `acknowledge_incident`, `assign_incident`, `add_incident_comment`,
  `close_incident`, `update_incident_state`
- `assign_task`, `add_task_comment`, `resolve_task`
- Respond `run_playbook`, API-key create/edit/delete — finalized
  post-introspection

## 8. Schema discovery workflow

The published API reference at `apidocs.myreliaquest.com` is a JS-rendered
Postman portal requiring a free Postman account, so it is **not directly
machine-readable**. Authoritative field names come from two sources:

1. **Exported Postman collection** (primary for curated tools). The maintainer
   exports the GreyMatter collection JSON and places it in
   `Development Reference/`. Curated tools are built from these real request
   examples.
2. **Live introspection** (full coverage + verification). `scripts/introspect.py`
   reads `GREYMATTER_API_KEY` from `.env`, runs the standard introspection
   query, and writes `schema/schema.graphql` + `schema.json`. Used to verify
   curated tools and to build out Detect/Respond/Metrics/API-Key/Assets tools.

Implementation of schema-specific tools begins once the Postman collection JSON
is available; the scaffolding (config, client, errors, server, escape hatch,
CI, tests harness) can be built before then.

## 9. Server entrypoint (`server.py` / `__main__`)

`build_server()` validates config early, configures logging to stderr (stdio
transport owns stdout), instantiates `FastMCP` with an `instructions` string
(noting the read-only toggle and OpCo `customer_slug` usage), and calls
`register_all`. `main()` provides argparse for `--transport {stdio,http}` plus
`--host/--port`, and shuts the shared client down cleanly on exit. Mirrors the
ThreatLocker entrypoint.

## 10. Error handling

- Config errors → exit code 2 with a clear stderr message.
- Transport/HTTP errors → `GreyMatterAPIError` surfaced to the tool caller.
- GraphQL `errors` array → `GreyMatterGraphQLError` with the messages, so the
  model sees *why* an operation failed (bad enum, missing permission, etc.).
- Empty/`null` data → returned explicitly so "no results" is distinguishable
  from a missing response.

## 11. Testing

pytest + pytest-httpx, mocking the `/graphql` POST. One test module per tool
module, plus client tests covering: GraphQL-error-on-HTTP-200, retry/backoff on
429/5xx, `Retry-After` handling, read-only gating (mutation tools absent), and
`customer_slug` header propagation. Config tests cover required/optional env
parsing. Mirrors the reference repos' test style.

## 12. CI / release

`.github/workflows/ci.yml` (ruff + pytest on 3.10–3.12) and `release.yml`
(build + publish), patterned on the reference repos.

## 13. Open items (resolved during implementation)

- Exact GraphQL field names and full enum sets — from Postman collection +
  introspection.
- Whether an `assets` query exists in the live schema (DataBee implies yes).
- Detect / Respond / Metrics / API-Key operation signatures.
