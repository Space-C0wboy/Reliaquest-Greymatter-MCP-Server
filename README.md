# ReliaQuest GreyMatter MCP Server

[![PyPI version](https://img.shields.io/pypi/v/greymatter-mcp.svg)](https://pypi.org/project/greymatter-mcp/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://pypi.org/project/greymatter-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server/actions/workflows/ci.yml/badge.svg)](https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server/actions/workflows/ci.yml)

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the
**ReliaQuest GreyMatter** Self-Service GraphQL API to AI assistants. It provides
**146 tools across 22 domains** — Incidents, Tasks, Detections, Playbooks, Cases, DRP
Alerts, Assets, Identities, Reference Lists, Users, and more — plus a generic
`graphql_query` escape hatch for anything not covered by a dedicated tool. The tool set
is generated directly from the vendor's API collection, so it stays faithful to the real
API surface, and it has been verified against the live GraphQL schema.

> [!IMPORTANT]
> **Unofficial project.** This is an independent, community-built MCP server developed
> against ReliaQuest's published API documentation. It is **not** an official ReliaQuest
> product and is not affiliated with, endorsed by, or supported by ReliaQuest, LLC.
> "ReliaQuest" and "GreyMatter" are trademarks of ReliaQuest, LLC. For official support of
> the GreyMatter platform or the API itself, contact ReliaQuest directly at
> [greymattersupport@reliaquest.com](mailto:greymattersupport@reliaquest.com).

> [!WARNING]
> **Beta software — not yet recommended for production environments.** This project is
> under active development. The tool surface and individual tool body shapes may still
> change between minor versions, and not every endpoint has been exhaustively exercised
> against every account/entitlement configuration. Use against a non-production scope until
> you're confident in the behavior for your use case.
>
> **This server can perform destructive actions against your GreyMatter environment.**
> Tools can close and cancel incidents/cases/tasks, run response playbooks, and create or
> delete users, API keys, access-control policies, and reference lists. A hallucinated tool
> argument from your AI assistant could change incident state or modify your tenant
> configuration.
>
> **Recommended posture:**
> - **Run read-only first.** Set `GREYMATTER_READ_ONLY=true` to register only query tools
>   and make `graphql_query` reject mutations. Lift it only when you need to write.
> - Use a GreyMatter API key scoped to the **minimum permissions** your use case requires.
> - Review every mutating tool call before allowing execution. Claude Desktop requires
>   tool-call approval by default — keep that enabled.
> - Treat the API key with the same care as portal admin credentials, because functionally
>   it is one.
> - The HTTP transport binds to `127.0.0.1` by default. Do not expose it to the public
>   internet without adding authentication.

## Tools

146 tools across 22 domains (56 queries + 90 mutations), plus the `graphql_query` escape
hatch. In read-only mode only the 56 queries (and a query-only `graphql_query`) are
registered.

| Domain | Queries | Mutations | Notable tools |
|--------|:-------:|:---------:|---------------|
| Incidents | 3 | 10 | `incidents`, `incident`, `health_incidents`, `acknowledge_incident`, `assign_incident`, `add_incident_comment`, `close_incident`, `update_incident_state` |
| Tasks | 2 | 9 | `tasks`, `task`, `assign_task`, `add_task_comment`, `resolve_task`, `update_task_state` |
| Detections | 6 | 1 | `detection_rules`, `customer_detections`, `customer_detection`, `customer_detection_activity_log_entries` |
| Playbooks | 6 | 4 | `playbooks`, `playbook_runs`, `playbook_run`, `recommended_playbooks`, `run_playbook` |
| Cases | 2 | 9 | `cases`, `case`, `create_case`, `close_case`, `cancel_case`, `add_case_comment`, `update_case_owner` |
| DRP Alerts | 2 | 15 | `drp_alerts`, `drp_alert`, `assign_drp_alert`, `watch_drp_alert`, `add_drp_alert_comment`, `update_drp_alert_state` |
| DRP Access Control | 3 | 4 | `access_control_policies`, `access_control_resources`, `create_access_control_policy` |
| Access Groups | 7 | 9 | `access_groups`, `pods`, `roles`, `permissions`, `create_role`, `update_pod` |
| Reference Lists | 2 | 9 | `reference_lists`, `reference_list`, `create_reference_list_row`, `update_reference_list_column` |
| Users | 2 | 9 | `me`, `user`, `create_user`, `disable_user`, `reset_mfa`, `resend_invite` |
| Discover Tasks | 2 | 3 | `discover_tasks`, `discover_task`, `assign_discover_task`, `close_discover_task` |
| Emergency Contacts | 2 | 4 | `emergency_contacts`, `create_emergency_contact`, `update_call_order` |
| API Keys | 1 | 3 | `api_keys`, `create_api_key`, `delete_api_key_by_id` |
| Assets | 1 | 1 | `assets`, `delete_asset` |
| Customer | 2 | 0 | `customer`, `customers` |
| Identities | 1 | 0 | `identities` |
| Indicators | 2 | 0 | `indicators`, `indicator` |
| Fields | 2 | 0 | `greymatter_fields`, `greymatter_field` |
| Query Management | 3 | 0 | `integrations`, `integration`, `search_history` |
| Data | 2 | 0 | `data_source_schema`, `time_buckets` |
| User Activity | 1 | 0 | `audits` |
| Utilities | 2 | 0 | `rate_limit`, `node` |

**146 tools total.** Highlights:

- **List queries** (`incidents`, `tasks`, `assets`, `detection_rules`, `cases`, …) are
  Relay-paginated — pass `first`/`after` and read `edges`, `pageInfo`, and `totalCount`.
  Most accept a domain filter and order input (e.g. `incidentFilter`, `incidentOrder`).
- **Single-item queries** (`incident`, `task`, `case`, `user`, …) take a `by` argument
  (e.g. an id or ticket number) to fetch one record with its full detail and comments.
- **Incident workflow** mutations cover the GreyMatter Investigate lifecycle:
  `acknowledge_incident`, `assign_incident`, `add_incident_comment`,
  `update_incident_state`, and `close_incident`. Incident close codes include
  `CUSTOMER_TRUE_POSITIVE`, `CUSTOMER_FALSE_POSITIVE`, `CUSTOMER_ANOMALOUS_SAFE`,
  `FALSE_POSITIVE_CREATE_TUNING_TICKET`, `CUSTOMER_SECURITY_CONTROL_TESTING`,
  `CUSTOMER_CANCELLED`; states include `PENDING_CUSTOMER`, `PENDING_RQ`, `RESOLVED`,
  `CANCELLED`.
- **Respond / playbooks:** `run_playbook` executes a predefined playbook; `playbook_runs`
  and `playbook_run` read execution results.
- **`graphql_query` escape hatch** runs an arbitrary GraphQL document for anything without
  a dedicated tool. In read-only mode it rejects mutations.
- **`customer_slug` on every tool** overrides the `x-reliaquest-customer` (OpCo) header for
  that single call — see [Multi-OpCo](#multi-opco-header-slug).
- **`rate_limit`** reports your remaining API budget (the API allows 5000 points/hour per
  company account; each returned node counts as one point).

See [`docs/ENDPOINTS.md`](docs/ENDPOINTS.md) for the full tool ↔ GraphQL-operation mapping.

## Quick start

### Install

```bash
# with uv (recommended)
uv tool install greymatter-mcp

# or with pip
pip install greymatter-mcp
```

For development from source:

```bash
git clone https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server
cd Reliaquest-Greymatter-MCP-Server
uv venv && uv pip install -e ".[dev]"
```

### Getting an API key

Generate a GreyMatter API key from the portal:

1. In GreyMatter, go to **Settings → API Key Management**.
2. Click **New API Key**, choose an **Expiration Date** (default is 1 year), then
   **Create Key**.
3. Copy the key — it is shown **only once**. This is your `GREYMATTER_API_KEY`.

> [!IMPORTANT]
> Each user can hold **one** API key, and keys **cannot be renewed** — creating a new key
> invalidates the old one. Requests authenticate with the `X-API-KEY` header (not your
> email/password login).

### Configuration

Copy `.env.example` to `.env` and set:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GREYMATTER_API_KEY` | **yes** | — | Your GreyMatter API key (Settings → API Key Management) |
| `GREYMATTER_BASE_URL` | no | `https://greymatter.myreliaquest.com/graphql` | GraphQL endpoint |
| `GREYMATTER_CUSTOMER_SLUG` | no | _(none)_ | Default `x-reliaquest-customer` (OpCo) header for multi-OpCo accounts |
| `GREYMATTER_READ_ONLY` | no | `false` | When true, no mutation tools are registered and `graphql_query` rejects mutations |
| `GREYMATTER_TIMEOUT` | no | `60` | Request timeout in seconds (some mutations are slow server-side) |
| `LOG_LEVEL` | no | `INFO` | Logging level |
| `MCP_HTTP_HOST` / `MCP_HTTP_PORT` | no | `127.0.0.1:8765` | HTTP transport bind |

### Run

- stdio (default): `uv run greymatter-mcp` (or just `greymatter-mcp` if installed as a tool)
- HTTP: `greymatter-mcp --transport http --port 8765`

## Read-only mode

Set `GREYMATTER_READ_ONLY=true` to run the server safely against production. In this mode:

- **No mutation tools are registered** — only the 56 query tools are exposed.
- **The `graphql_query` escape hatch rejects mutations**, so it can only run read
  operations (robust against fragment- or BOM-prefixed mutation documents).

Read-only mode is strongly recommended for analyst-assistant, dashboard, and reporting use
cases where the model should never be able to change state.

## Editor integration

### Claude Desktop

Edit `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "greymatter": {
      "command": "greymatter-mcp",
      "env": {
        "GREYMATTER_API_KEY": "your-key-here",
        "GREYMATTER_READ_ONLY": "true"
      }
    }
  }
}
```

If running from source instead of an installed tool, use `uv` with `--directory`:

```json
{
  "mcpServers": {
    "greymatter": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/Reliaquest-Greymatter-MCP-Server", "greymatter-mcp"],
      "env": { "GREYMATTER_API_KEY": "your-key-here", "GREYMATTER_READ_ONLY": "true" }
    }
  }
}
```

Restart Claude Desktop, then confirm `greymatter` appears in the tools menu.

### Claude Code

```bash
claude mcp add greymatter \
  --env GREYMATTER_API_KEY=your-key-here \
  --env GREYMATTER_READ_ONLY=true \
  -- greymatter-mcp
```

## Multi-OpCo (Header Slug)

GreyMatter accounts that manage multiple operating companies (OpCos) use the
`x-reliaquest-customer` header ("Header Slug") to select which company a request targets:

- Set `GREYMATTER_CUSTOMER_SLUG` to apply a default slug to every request.
- Pass `customer_slug` on any individual tool call to override the default for that call.
  Both set the `x-reliaquest-customer` header.

## Rate limits

The GreyMatter API enforces a limit of **5000 points/hour per company account**. Each node
entity returned counts as **1 point**, so large paginated queries consume points quickly.
Use the **`rate_limit`** tool to check your current usage.

## Known limitations

**Entitlement-gated tools.** Some tools return *"You don't have access to this item"*
unless your account/API key is licensed for the relevant module — e.g. `drp_alerts`,
`access_control_policies`, `access_control_resources`, `discover_tasks`, `audits`. These
work normally for entitled accounts.

**Multi-connection queries.** A few queries page several nested connections and expose
multiple `first` / `after` parameters (e.g. `cases` uses `first3`/`after3` for the
top-level list and `first`/`first1`/`first2` for nested connections). Always set the
**outer** page-size parameter to bound results; leaving it unset can return very large
responses and time out. For heavy queries (e.g. `playbook_run_filter_data`), raise
`GREYMATTER_TIMEOUT`.

## Example prompts

- *"Show me incidents pending customer action."* → `incidents` (filter on
  `state: PENDING_CUSTOMER`).
- *"Acknowledge incident `<id>` and assign it to me."* → `acknowledge_incident` →
  `assign_incident`.
- *"Resolve incident `<id>` as a false positive with a tuning note."* → `close_incident`
  (`closeCode: CUSTOMER_FALSE_POSITIVE`).
- *"What detection rules are deployed, and which map to MITRE techniques?"* →
  `detection_rules`.
- *"List the 25 most recent open cases."* → `cases` (set `first3: 25`).
- *"How much of my API rate-limit budget is left?"* → `rate_limit`.

## How tools are generated

The tools are generated from the vendor's API collection:

```bash
python scripts/generate_from_collection.py
```

This regenerates the modules under `src/greymatter_mcp/tools/_generated/` and the catalog
at `docs/ENDPOINTS.md`. The generated files are **not hand-edited** — change the generator
(its `OVERRIDES` / `FIELD_EXCLUSIONS` maps) and regenerate.

The API collection and other ReliaQuest reference material live in the
`Development Reference/` directory, which is **gitignored**: it is ReliaQuest proprietary
material and is not redistributed in this public repository. To verify the generated tools
against the live API, `scripts/introspect.py` fetches the current GraphQL schema.

## Development

```bash
uv run pytest        # full suite (HTTP fully mocked; no live calls)
uv run ruff check .  # lint
uv run python scripts/generate_from_collection.py  # regenerate tools
```

Releases publish to PyPI when a `v*` tag is pushed (see `.github/workflows/release.yml`).

## License

[MIT](LICENSE)

## Support

This is an unofficial community project. For GreyMatter platform or API questions, contact
ReliaQuest at [greymattersupport@reliaquest.com](mailto:greymattersupport@reliaquest.com).
For issues with this MCP server, open an issue on the
[GitHub repository](https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server/issues).
