"""Fetch the live GreyMatter GraphQL schema via introspection.

This MCP server exposes the ReliaQuest GreyMatter GraphQL API. The companion generator
(scripts/generate_from_collection.py) builds the tool modules from the vendor's *Postman
collection*, which can drift from what the server actually accepts. This script is the
verification side: it asks the live API for its schema using a standard GraphQL
introspection query, then writes the result out so the documents the generator emits can
be checked against the real types, fields, and enum values.

Usage:
    python scripts/introspect.py

Reads GREYMATTER_API_KEY (and optional GREYMATTER_BASE_URL,
GREYMATTER_CUSTOMER_SLUG) from the environment / .env (via greymatter_mcp.config). Writes:
  - schema/schema.json     — the raw introspection payload (full machine-readable schema).
  - schema/schema.graphql  — a trimmed, human-readable SDL-style summary for eyeballing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from greymatter_mcp.config import get_config

# Standard GraphQL introspection query. The __schema meta-field describes the whole API:
# every type, its fields (with their args), input-object fields, and enum values. We include
# deprecated members so the dump is a complete picture. The TypeRef fragment unwraps wrapper
# types (NON_NULL / LIST) up to three levels deep via ofType — enough to express common shapes
# like [Foo!]! without an unbounded recursive query (GraphQL has no recursive fragments).
_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind name description
      fields(includeDeprecated: true) {
        name description
        args { name description type { ...TypeRef } }
        type { ...TypeRef }
      }
      inputFields { name description type { ...TypeRef } }
      enumValues(includeDeprecated: true) { name description }
    }
  }
}
fragment TypeRef on __Type {
  kind name
  ofType { kind name ofType { kind name ofType { kind name } } }
}
"""


def _sdl_from_introspection(schema: dict) -> str:
    """Render a minimal, human-readable SDL-style summary from the introspection payload.

    Args:
        schema: The "__schema" object from the introspection response.

    Returns:
        A multi-line string listing each type with its field names (for objects/inputs/
        interfaces) or its value names (for enums). Not valid SDL — field types/args are
        intentionally omitted; this is a quick-reference dump, not a re-importable schema.

    Why: the raw schema.json is exhaustive but hard to skim. This gives a reviewer a compact
    "what types/fields/enums exist" view to sanity-check generated documents against.

    Notes: types are sorted by name for stable diffs, and introspection meta-types (names
    starting with "__") are skipped since they describe the introspection system itself.
    """
    lines: list[str] = []
    for t in sorted(schema["types"], key=lambda x: x.get("name") or ""):  # stable, sorted output
        name = t.get("name") or ""
        if name.startswith("__"):
            continue   # skip introspection meta-types (e.g. __Type, __Schema)
        kind = t.get("kind")
        if kind in ("OBJECT", "INPUT_OBJECT", "INTERFACE"):
            lines.append(f"{kind} {name} {{")
            # Objects/interfaces expose "fields"; input objects expose "inputFields".
            for f in (t.get("fields") or t.get("inputFields") or []):
                lines.append(f"  {f['name']}")
            lines.append("}")
        elif kind == "ENUM":
            vals = ", ".join(v["name"] for v in (t.get("enumValues") or []))
            lines.append(f"ENUM {name} {{ {vals} }}")
        lines.append("")   # blank line between types for readability
    return "\n".join(lines)


def main() -> int:
    """Run the introspection request and write schema.json + schema.graphql.

    Returns:
        Process exit code: 1 if the API returned GraphQL errors, otherwise 0. (Transport/HTTP
        failures surface as exceptions via raise_for_status rather than a return code.)

    Reads credentials/endpoint from greymatter_mcp.config (env / .env). The customer-slug
    header is sent only when configured, since single-tenant accounts don't need it.
    """
    cfg = get_config()
    headers = {"X-API-KEY": cfg.api_key, "Content-Type": "application/json"}
    if cfg.customer_slug:
        headers["x-reliaquest-customer"] = cfg.customer_slug   # target a specific OpCo

    resp = httpx.post(
        cfg.base_url, json={"query": _INTROSPECTION_QUERY}, headers=headers, timeout=cfg.timeout
    )
    resp.raise_for_status()   # raise on HTTP-level failure (4xx/5xx)
    payload = resp.json()
    # GraphQL can return HTTP 200 with an "errors" array — treat that as a failure too.
    if payload.get("errors"):
        print(json.dumps(payload["errors"], indent=2), file=sys.stderr)
        return 1

    schema = payload["data"]["__schema"]
    out = Path("schema")
    out.mkdir(exist_ok=True)
    # Persist both views: the full raw payload, and the trimmed human-readable summary.
    (out / "schema.json").write_text(json.dumps(payload["data"], indent=2), encoding="utf-8")
    (out / "schema.graphql").write_text(_sdl_from_introspection(schema), encoding="utf-8")
    print(f"Wrote schema/schema.json and schema/schema.graphql ({len(schema['types'])} types)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
