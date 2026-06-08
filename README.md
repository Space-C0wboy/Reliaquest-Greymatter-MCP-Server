# ReliaQuest GreyMatter MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for the
[ReliaQuest GreyMatter](https://www.reliaquest.com/) GraphQL API. It exposes **146
curated tools across 22 domains** — incidents, tasks, detections, playbooks, cases,
DRP alerts, access groups, users, assets, and more — plus a generic `graphql_query`
escape hatch for anything not covered by a dedicated tool. The tool set is generated
directly from the vendor's Postman collection, so it stays faithful to the real API
surface, and it has been verified against the live GraphQL schema.

This is a community project and is not officially affiliated with or endorsed by
ReliaQuest, LLC.

## Features

- **Full domain coverage** — 146 generated GraphQL tools spanning all 22 GreyMatter
  domains, grouped by domain for easy discovery.
- **Read-only safety toggle** — `GREYMATTER_READ_ONLY=true` hides every mutation tool
  and makes the escape hatch reject mutations.
- **Multi-OpCo support** — set a default customer slug globally and override it
  per call via the `x-reliaquest-customer` header.
- **Escape hatch** — a generic `graphql_query` tool for operations without a
  dedicated wrapper.
- **Retry / backoff** — an async GraphQL client with retry, backoff, and structured
  GraphQL-error handling.
- **Introspection-verified** — the generated tools are checked against the live
  GraphQL schema fetched via `scripts/introspect.py`.

## Requirements

- **Python >= 3.10**
- A **GreyMatter API key**, generated from **GreyMatter > Settings > API Key
  Management**.

## Installation

Create a virtual environment and install the package (with dev extras for tests and
linting):

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

[`uv`](https://github.com/astral-sh/uv) works too:

```bash
uv venv
uv pip install -e ".[dev]"
```

## Configuration

Configuration is read from environment variables (a `.env` file is supported via
`python-dotenv`). Copy the example file and fill in your key:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `GREYMATTER_API_KEY` | **Yes** | — | Your GreyMatter API key (GreyMatter > Settings > API Key Management). |
| `GREYMATTER_BASE_URL` | No | `https://greymatter.myreliaquest.com/graphql` | GraphQL endpoint. |
| `GREYMATTER_CUSTOMER_SLUG` | No | _(none)_ | Default `x-reliaquest-customer` (OpCo) header for multi-OpCo accounts. |
| `GREYMATTER_READ_ONLY` | No | `false` | When true, no mutation tools are registered and `graphql_query` rejects mutations. |
| `GREYMATTER_TIMEOUT` | No | `30` | Request timeout in seconds. |
| `LOG_LEVEL` | No | `INFO` | Logging level. |
| `MCP_HTTP_HOST` | No | `127.0.0.1` | Bind host for the HTTP transport. |
| `MCP_HTTP_PORT` | No | `8765` | Bind port for the HTTP transport. |

## Read-only mode

Set `GREYMATTER_READ_ONLY=true` to run the server safely against production. In this
mode:

- **No mutation tools are registered** — only queries are exposed.
- **The `graphql_query` escape hatch rejects mutations**, so it can only run read
  operations.

Read-only mode is strongly recommended for any read-only use case (dashboards,
reporting, analyst assistants) where the model should never be able to change state.

## Usage with Claude Desktop

Add the server to your Claude Desktop MCP configuration:

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

You can also run the server directly:

```bash
# stdio transport (default)
greymatter-mcp

# HTTP transport
greymatter-mcp --transport http --port 8765
```

## Tools

Tools are grouped by GreyMatter domain (incidents, tasks, detections, playbooks,
cases, DRP alerts, access groups, users, assets, and more). See
[`docs/ENDPOINTS.md`](docs/ENDPOINTS.md) for the full, auto-generated catalog of every
tool and its underlying GraphQL operation.

For operations that don't have a dedicated tool, use the generic **`graphql_query`**
escape hatch to run an arbitrary GraphQL document. Every tool also accepts an optional
`customer_slug` argument to override the OpCo header for that single call (see below).

## Multi-OpCo (Header Slug)

GreyMatter accounts that manage multiple operating companies (OpCos) use the
`x-reliaquest-customer` header ("Header Slug") to select which company a request
targets:

- Set `GREYMATTER_CUSTOMER_SLUG` to apply a default slug to every request.
- Pass `customer_slug` on any individual tool call to override the default for that
  call. Both set the `x-reliaquest-customer` header.

## Rate limits

The GreyMatter API enforces a limit of **5000 points/hour per company account**. Each
node entity returned counts as **1 point**, so large paginated queries consume points
quickly. Use the **`rate_limit`** tool to check your current usage.

## How tools are generated

The tools are generated from the vendor's Postman collection:

```bash
python scripts/generate_from_collection.py
```

This regenerates the modules under `src/greymatter_mcp/tools/_generated/` and the
catalog at `docs/ENDPOINTS.md`. The generated files are **not hand-edited** — change
the generator (or the override map inside it) and regenerate.

The Postman collection and other ReliaQuest reference material live in the
`Development Reference/` directory, which is **gitignored**: it is ReliaQuest
proprietary material and is not redistributed in this public repository. To verify the
generated tools against the live API, `scripts/introspect.py` fetches the current
GraphQL schema.

## Development

```bash
# Run the test suite
pytest

# Lint
ruff check .

# Regenerate tools from the Postman collection
python scripts/generate_from_collection.py
```

## License

[MIT](LICENSE)

## Support

For GreyMatter API questions, contact ReliaQuest support at
[greymattersupport@reliaquest.com](mailto:greymattersupport@reliaquest.com).
