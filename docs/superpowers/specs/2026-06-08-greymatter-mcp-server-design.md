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
so operators get a consistent experience and the codebase is familiar to
maintainers.

The key difference from those two servers: GreyMatter is a **single GraphQL
endpoint**, not a REST API. The architecture is adapted accordingly.

This will be released as a **public/community project** under the maintainer's
personal GitHub account (Space-C0wboy); commits use the noreply community email.

## 2. Background — the GreyMatter API

- **Endpoint:** `POST https://greymatter.myreliaquest.com/graphql` (single URL).
- **Protocol:** GraphQL. All requests are HTTP POST with a JSON body of
  `{"query": "...", "variables": {...}}`.
- **Auth:** header `X-API-KEY: <key>`. No bearer scheme; not email/password.
  Each user may hold one key; keys expire (default 1 year) and cannot be renewed
  (must be recreated).
- **Multi-OpCo:** accounts managing multiple operating companies send an
  additional `x-reliaquest-customer` header (the "Header Slug") to target a
  specific company.
- **Introspection:** enabled — schema queryable directly.
- **Rate limiting:** 5000 points per company account per hour; each Node entity
  in a request counts as one point. (A `rateLimit` query exists to check usage.)
- **Pagination:** cursor-based (syncing) and offset-based (retrieval). Connections
  follow the Relay pattern (`edges { cursor node }`, `pageInfo`, `totalCount`).
- **GraphQL error semantics:** a `200 OK` response can still contain an `errors`
  array; the client must inspect the body, not just the HTTP status.

### Authoritative source: the Postman collection

The published reference at `apidocs.myreliaquest.com` is a JS-rendered Postman
portal requiring a free Postman account, so it is **not directly
machine-readable**. The maintainer exported the collection to
`Development Reference/GreyMatter API.postman_collection.json` (~1.2 MB). This is
the **primary source of truth** for tool generation: it contains the exact,
ReliaQuest-authored GraphQL document (query/mutation, with curated selection
sets) and example variables for every operation. Live introspection
(`scripts/introspect.py`) is a secondary source used for verification and to
fill any gaps.

### Full operation surface (~150 operations across 22 domains)

The collection is far broader than the four reference PDFs implied. Domains:

| Domain | Queries | Mutations |
|---|---|---|
| **Incidents** | `incidents`, `incident`, `healthIncidents` | acknowledge, addComment, assign, close, updateState, bulkClose, retain, release, unresolve, acknowledgeAssignAndClose |
| **Tasks** | `tasks`, `task` | acknowledge, addComment, assign, resolve, unresolve, bulkResolve, create, updateState, updateRetainedStatus |
| **Detections** | `detectionRules`, `customerDetection(s)`, `customerDetectionActivityLogEntr(y/ies)`, `draftCustomerDetection` | createActivityLogEntryComment |
| **Playbooks** (Respond) | `playbooks`, `playbookRun(s)`, `customerPlaybooks`, `recommendedPlaybooks`, `playbookRunFilterData` | runPlaybook, rerunAllFailedTasksForPlaybookRun, upsertCustomerPlaybook, upsertPlaybookMetadata |
| **Cases** | `case`, `cases` | create, close, cancel, update, updateDueDate, updateOwner, addComment, addChildrenToCase, removeChildFromCase |
| **DRP Alerts** | `drpAlert`, `drpAlerts` | assign(s), unassign(s), watch(es), unWatch(es), addComment, bulkAddComment, updateComment, deleteComment, updateState, bulkUpdateState, bulkClose |
| **DRP Access Control** | `accessControlPolicy(ies)`, `accessControlResources` | create, update, updatePolicies, delete |
| **Access Groups** | `accessGroup(s)`, `pod(s)`, `role(s)`, `permissions` | create/update/delete × accessGroup/pod/role |
| **User** | `me`, `user` | create, update, delete, disable, enable, resetMfa, resendInvite, generatePasswordLink, sendForgotPassword |
| **Customer** | `customer`, `customers` | — |
| **Identities** | `identities` | — |
| **Assets** | `assets` | deleteAsset |
| **Indicators** | `indicator`, `indicators` | — |
| **Discover Tasks** | `discoverTask(s)` | assign, close, updateState |
| **Emergency Contacts** | `emergencyContact(s)` | create, update, delete, updateCallOrder |
| **Reference Lists** | `referenceList(s)` | create/update/delete × list/column/row |
| **Fields** | `greymatterField(s)` | — |
| **Query Management** | `integration(s)`, `searchHistory` | — |
| **User Activity** | `audits` | — |
| **Data** | `dataSourceSchema`, `timeBuckets` | — |
| **API Keys** | `apiKeys` | createApiKey, deleteApiKeyById, deleteApiKeys |
| **Utilities** | `node`, `rateLimit` | — |

Documented enums (from PDFs; full sets verified from collection/introspection):
- Incident states: `PENDING_CUSTOMER`, `PENDING_RQ`, `RESOLVED`, `CANCELLED`, …
- Incident close codes: `CUSTOMER_ANOMALOUS_SAFE`, `CUSTOMER_FALSE_POSITIVE`,
  `CUSTOMER_TRUE_POSITIVE`, `FALSE_POSITIVE_CREATE_TUNING_TICKET`,
  `CUSTOMER_SECURITY_CONTROL_TESTING`, `CUSTOMER_CANCELLED`.
- Task close codes: `CANCELLED`, `DUPLICATE`, `RESOLVED`.
- Comment types: `PUBLIC`, … ; acknowledgement method: `WEB_UI`, …

## 3. Goals & non-goals

**Goals**
- Cover the **entire** documented operation surface (all 22 domains, ~150
  operations) as dedicated curated tools, generated from the Postman collection.
- A generic `graphql_query` escape hatch for anything not covered or new.
- Match the reference repos' layout, tooling, and conventions.
- Safe-by-option: a single read-only toggle that hides every mutating tool.
- Regenerable: re-running the generator against an updated collection refreshes
  all tools deterministically.

**Non-goals**
- Returning query-log results (Main Search / Targeted Query) — excluded by the
  GreyMatter API itself.
- Building new detection queries against client technology — out of API scope.
- A hand-written pydantic model for every response type. Responses are returned
  as parsed JSON; the GraphQL selection set (from the collection) determines
  shape. Typed input models are derived where it adds value.

## 4. Architecture & approach

**Collection-driven generation (curated-by-vendor, automated).** At ~150
operations, tools are produced by a generator (`scripts/generate_from_collection.py`)
that reads the exported Postman collection and emits one tool per operation:

- **Query string:** used verbatim from the collection (preserves ReliaQuest's
  curated selection sets — resolves the "GraphQL selection sets need human
  judgment" concern, since a human at the vendor already authored them).
- **Tool name:** snake_case of the GraphQL operation name (e.g. `acknowledge_incident`,
  `list` semantics preserved as the vendor named them — `incidents`, `incident`).
  A small, reviewed name-map handles collisions/readability.
- **Module:** one Python module per collection folder/domain (e.g.
  `incidents.py`, `drp_alerts.py`).
- **Parameters:** the operation's GraphQL variable declarations
  (`$after: String, $first: Int, $incidentFilter: IncidentFilter`) are parsed
  into typed tool parameters — GraphQL scalars → Python types; input-object
  types → `dict` params whose description names the GraphQL input type (and, when
  known from the collection example, shows the shape). Every tool also takes an
  optional `customer_slug` override.
- **Description:** derived from folder + operation name + the variable shape;
  refined for the high-traffic SOC tools.
- **Mutation flag:** operations from a `mutation` document are marked so the
  read-only toggle can exclude them.

Introspection output verifies generated types/enums and flags drift.

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
│   └── ENDPOINTS.md                # generated operation → tool catalog (all domains)
├── scripts/
│   ├── generate_from_collection.py # Postman collection → tools/*.py (+ ENDPOINTS.md)
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
│   ├── tools/
│   │   ├── __init__.py             # register_all(mcp) + read-only gating
│   │   ├── _common.py              # shared param helpers, customer_slug plumbing
│   │   ├── _generated/             # one module per domain (generated; do not hand-edit)
│   │   │   ├── incidents.py
│   │   │   ├── tasks.py
│   │   │   ├── detections.py
│   │   │   ├── playbooks.py
│   │   │   ├── cases.py
│   │   │   ├── drp_alerts.py
│   │   │   ├── drp_access_control.py
│   │   │   ├── access_groups.py
│   │   │   ├── user.py
│   │   │   ├── customer.py
│   │   │   ├── identities.py
│   │   │   ├── assets.py
│   │   │   ├── indicators.py
│   │   │   ├── discover_tasks.py
│   │   │   ├── emergency_contacts.py
│   │   │   ├── reference_lists.py
│   │   │   ├── fields.py
│   │   │   ├── query_management.py
│   │   │   ├── user_activity.py
│   │   │   ├── data.py
│   │   │   ├── api_keys.py
│   │   │   └── utilities.py
│   │   └── graphql.py              # hand-written generic graphql_query escape hatch
└── tests/                          # pytest + pytest-httpx
└── .github/workflows/
    ├── ci.yml
    └── release.yml
```

## 6. Components

### 6.1 `config.py`
Env-based frozen `Config` dataclass, lazy `get_config()` singleton, `ConfigError`.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `GREYMATTER_API_KEY` | ✅ | — | `X-API-KEY` value |
| `GREYMATTER_BASE_URL` | | `https://greymatter.myreliaquest.com/graphql` | endpoint |
| `GREYMATTER_CUSTOMER_SLUG` | | — | default `x-reliaquest-customer` header (OpCo) |
| `GREYMATTER_READ_ONLY` | | `false` | when true, no mutation tools registered; `graphql_query` is query-only |
| `GREYMATTER_TIMEOUT` | | `30` | request timeout (seconds) |
| `LOG_LEVEL` | | `INFO` | logging level |
| `MCP_HTTP_HOST` | | `127.0.0.1` | HTTP transport bind host |
| `MCP_HTTP_PORT` | | `8765` | HTTP transport bind port |

### 6.2 `client.py`
Process-wide shared async `GreyMatterClient`:
- `execute(query, variables=None, *, customer_slug=None) -> Any` posts to the
  single endpoint, returns the `data` object.
- Sends `X-API-KEY`; adds `x-reliaquest-customer` when configured or passed.
- **GraphQL-aware errors:** raises `GreyMatterGraphQLError` when the body has a
  non-empty `errors` array (even on HTTP 200); `GreyMatterAPIError` on non-2xx.
- Retry/backoff with full jitter on network errors, 429, 5xx; honors
  `Retry-After` (capped). Logs rate-limit context.
- Lazy connect under a lock; clean `shutdown_client()`. Same lifecycle as the
  ThreatLocker client.

### 6.3 `errors.py`
`GreyMatterAPIError` (HTTP/transport; status + body) and
`GreyMatterGraphQLError` (GraphQL `errors` list).

### 6.4 `tools/_generated/*` and registration
Each generated module exposes `register(mcp, *, read_only: bool)`.
`register_all(mcp)` reads config and fans out; mutation tools are skipped when
`read_only`. Every tool takes an optional `customer_slug`. `graphql.py` is
hand-written and registered last.

### 6.5 `scripts/generate_from_collection.py`
Deterministic generator (see §4). Idempotent: same collection → same output.
Emits the `_generated/` modules and `docs/ENDPOINTS.md`. A header comment in each
generated file marks it as generated.

## 7. Tool inventory

All operations in §2's table become tools, one per operation, grouped by domain
module, plus the `graphql_query` escape hatch. Queries are always registered;
mutations only when `GREYMATTER_READ_ONLY` is false. `docs/ENDPOINTS.md`
(generated) is the authoritative catalog.

## 8. Schema discovery & generation workflow

1. **Generate** from the committed Postman collection:
   `python scripts/generate_from_collection.py` → writes `tools/_generated/*` and
   `docs/ENDPOINTS.md`.
2. **Verify** against the live schema: `python scripts/introspect.py` (reads
   `GREYMATTER_API_KEY` from `.env`) → writes `schema/schema.graphql` +
   `schema.json`; used to confirm input types/enums and detect drift.
3. Re-running step 1 after a collection update refreshes all tools.

## 9. Server entrypoint (`server.py` / `__main__`)

`build_server()` validates config early, logs to stderr (stdio owns stdout),
instantiates `FastMCP` with an `instructions` string (read-only toggle, OpCo
`customer_slug` usage, "call `rate_limit` to check budget"), and calls
`register_all`. `main()` provides argparse for `--transport {stdio,http}` plus
`--host/--port`, and shuts the shared client down cleanly. Mirrors the
ThreatLocker entrypoint.

## 10. Error handling

- Config errors → exit code 2 with a clear stderr message.
- Transport/HTTP errors → `GreyMatterAPIError`.
- GraphQL `errors` array → `GreyMatterGraphQLError` with messages, so the model
  sees *why* an op failed (bad enum, missing permission, rate limit, …).
- Empty/`null` data → returned explicitly so "no results" ≠ missing response.

## 11. Testing

pytest + pytest-httpx mocking the `/graphql` POST. Coverage:
- **Client:** GraphQL-error-on-HTTP-200, retry/backoff on 429/5xx,
  `Retry-After`, `customer_slug` header propagation.
- **Config:** required/optional env parsing, read-only parsing.
- **Generator:** golden test — generate from a small fixture collection and
  assert the emitted module/tool shape (names, mutation flags, params).
- **Registration:** `register_all` with `read_only=True` registers zero mutation
  tools and a query-only `graphql_query`; with `read_only=False` registers the
  full set. Spot-check representative generated tools per tier.

## 12. CI / release

`.github/workflows/ci.yml` (ruff + pytest on 3.10–3.12) and `release.yml`
(build + publish), patterned on the reference repos. CI optionally re-runs the
generator and fails if `_generated/` is out of date with the collection.

## 13. Open items (resolved during implementation)

- Final tool-name map (readability/collision handling) — reviewed during
  generator implementation.
- Exact input-object field shapes and full enum sets — from collection examples,
  confirmed via introspection.
- How rich to make typed params for deeply-nested input objects vs. accepting a
  `dict` — decided per domain during generation (lean `dict`-with-described-shape
  for complex inputs; typed scalars for simple ones).
