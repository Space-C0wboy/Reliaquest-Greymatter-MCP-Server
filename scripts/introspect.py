"""Fetch the live GreyMatter GraphQL schema via introspection.

Usage:
    python scripts/introspect.py

Reads GREYMATTER_API_KEY (and optional GREYMATTER_BASE_URL,
GREYMATTER_CUSTOMER_SLUG) from the environment / .env. Writes
schema/schema.json (raw introspection) and schema/schema.graphql (SDL summary).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from greymatter_mcp.config import get_config

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
    """Minimal SDL-ish summary: type names, fields, enum values. Human reference only."""
    lines: list[str] = []
    for t in sorted(schema["types"], key=lambda x: x.get("name") or ""):
        name = t.get("name") or ""
        if name.startswith("__"):
            continue
        kind = t.get("kind")
        if kind in ("OBJECT", "INPUT_OBJECT", "INTERFACE"):
            lines.append(f"{kind} {name} {{")
            for f in (t.get("fields") or t.get("inputFields") or []):
                lines.append(f"  {f['name']}")
            lines.append("}")
        elif kind == "ENUM":
            vals = ", ".join(v["name"] for v in (t.get("enumValues") or []))
            lines.append(f"ENUM {name} {{ {vals} }}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    cfg = get_config()
    headers = {"X-API-KEY": cfg.api_key, "Content-Type": "application/json"}
    if cfg.customer_slug:
        headers["x-reliaquest-customer"] = cfg.customer_slug

    resp = httpx.post(
        cfg.base_url, json={"query": _INTROSPECTION_QUERY}, headers=headers, timeout=cfg.timeout
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        print(json.dumps(payload["errors"], indent=2), file=sys.stderr)
        return 1

    schema = payload["data"]["__schema"]
    out = Path("schema")
    out.mkdir(exist_ok=True)
    (out / "schema.json").write_text(json.dumps(payload["data"], indent=2), encoding="utf-8")
    (out / "schema.graphql").write_text(_sdl_from_introspection(schema), encoding="utf-8")
    print(f"Wrote schema/schema.json and schema/schema.graphql ({len(schema['types'])} types)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
