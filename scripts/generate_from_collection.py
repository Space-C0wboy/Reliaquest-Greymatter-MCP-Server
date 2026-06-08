"""Generate FastMCP tool modules from the GreyMatter Postman collection.

Usage:
    python scripts/generate_from_collection.py [COLLECTION_JSON]

Defaults to "Development Reference/GreyMatter API.postman_collection.json".
Writes src/greymatter_mcp/tools/_generated/<domain>.py, _generated/__init__.py,
and docs/ENDPOINTS.md. Deterministic: same collection -> same output.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULT_COLLECTION = Path("Development Reference/GreyMatter API.postman_collection.json")
DEFAULT_OUT_DIR = Path("src/greymatter_mcp/tools/_generated")
DEFAULT_DOC = Path("docs/ENDPOINTS.md")

_SCALAR_ANNOT = {
    "String": "str",
    "ID": "str",
    "Int": "int",
    "Float": "float",
    "Boolean": "bool",
}

# Richer descriptions for high-traffic SOC operations. Keyed by GraphQL operation
# name. These override the auto-generated description text (parameters are
# unaffected). Enum values below are from the GreyMatter API documentation.
OVERRIDES: dict[str, str] = {
    "incidents": "List security incidents with filtering (state, severity, updated time range) and ordering. Relay-paginated (edges/pageInfo/totalCount). Common states: PENDING_CUSTOMER, PENDING_RQ, RESOLVED, CANCELLED.",
    "incident": "Fetch a single incident by id or ticket number, including comments, artifacts, metadata, rule, and assignee.",
    "acknowledgeIncident": "Acknowledge an incident. input: IncidentAcknowledgementInput { incidentId, acknowledgementMethod (e.g. WEB_UI), autoAssign }.",
    "assignIncident": "Assign an incident to a GreyMatter user. input: AssignIncidentInput { incidentId, assigneeId }. Resolve assigneeId via the customer/users query.",
    "addIncidentComment": "Add a comment to an incident. input: IncidentCommentInput { incidentId, comment }.",
    "closeIncident": "Resolve or cancel an incident. request: CloseIncidentRequest { incidentId, state (RESOLVED or CANCELLED), closeCode, closeNote }. Incident close codes: CUSTOMER_ANOMALOUS_SAFE, CUSTOMER_FALSE_POSITIVE, CUSTOMER_TRUE_POSITIVE, FALSE_POSITIVE_CREATE_TUNING_TICKET, CUSTOMER_SECURITY_CONTROL_TESTING, CUSTOMER_CANCELLED.",
    "updateIncidentState": "Change an incident's state (e.g. send back to ReliaQuest). input: UpdateIncidentStateInput { incidentId, state (e.g. PENDING_RQ, PENDING_CUSTOMER), comment }.",
    "tasks": "List tasks (non-security / engineering items) with filtering and ordering. Relay-paginated.",
    "task": "Fetch a single task by id, including comments.",
    "assignTask": "Assign a task to a GreyMatter user. input: AssignTaskInput { taskId, assigneeId }.",
    "addTaskComment": "Add a comment to a task. input: TaskCommentInput { taskId, comment }.",
    "resolveTask": "Resolve a task. input: ResolveTaskInput { taskId, closeCode (CANCELLED, DUPLICATE, or RESOLVED), closeNote }.",
    "detectionRules": "List deployed detection rules across GreyMatter integrations (includes MITRE ATT&CK mapping where available).",
    "runPlaybook": "Execute a predefined playbook (Respond capability) with the given inputs.",
    "rateLimit": "Return current GreyMatter API rate-limit usage (limit is 5000 points/hour per company account).",
}

_OP_RE = re.compile(r"^\s*(query|mutation)\s+([A-Za-z0-9_]+)?\s*(\([^)]*\))?", re.DOTALL)


def parse_operation(query: str) -> tuple[str, str, str]:
    """Return (kind, operation_name, signature) for a GraphQL document."""
    m = _OP_RE.match(query)
    if not m:
        return ("query", "", "")
    kind = m.group(1)
    name = m.group(2) or ""
    sig = m.group(3) or ""
    return (kind, name, sig)


def parse_variable_decls(signature: str) -> list[tuple[str, str, bool]]:
    """Parse "($a: String, $b: Foo!)" -> [(name, type, required), ...]."""
    inner = signature.strip()
    if inner.startswith("("):
        inner = inner[1:]
    if inner.endswith(")"):
        inner = inner[:-1]
    inner = inner.strip()
    if not inner:
        return []
    out: list[tuple[str, str, bool]] = []
    for part in inner.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name_part, type_part = part.split(":", 1)
        name = name_part.strip().lstrip("$")
        gql_type = type_part.strip()
        required = gql_type.endswith("!")
        out.append((name, gql_type, required))
    return out


def py_annotation(gql_type: str) -> str:
    """Map a GraphQL type to a Python annotation string for the tool signature."""
    t = gql_type.strip()
    if t.startswith("["):
        return "list"
    base = t.rstrip("!")
    required = t.endswith("!")
    if base in _SCALAR_ANNOT:
        py = _SCALAR_ANNOT[base]
        return py if required else f"{py} | None"
    return "Any" if required else "Any | None"


def tool_name(op_name: str) -> str:
    """camelCase / PascalCase GraphQL field -> snake_case tool name."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", op_name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def module_name(folder: str) -> str:
    """Domain folder name -> valid snake_case module filename (no extension)."""
    s = folder.strip().replace("-", " ").replace("/", " ")
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^a-z0-9_]", "", s.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "mod_" + s
    return s


def _iter_requests(items, top_folder=None):
    """Yield (top_folder, request_dict) for every leaf request with a graphql body."""
    for it in items or []:
        name = it.get("name", "")
        if "item" in it:
            yield from _iter_requests(it["item"], top_folder or name)
        else:
            req = it.get("request") or {}
            body = req.get("body") or {}
            if body.get("mode") == "graphql" and body.get("graphql", {}).get("query"):
                yield (top_folder or "Misc", req)


def _collect(collection: dict) -> dict[str, list[dict]]:
    """Group operations by module name."""
    by_module: dict[str, list[dict]] = {}
    for folder, req in _iter_requests(collection.get("item", [])):
        gql = req["body"]["graphql"]
        query = gql["query"].strip()
        kind, op_name, sig = parse_operation(query)
        if not op_name:
            continue
        example = gql.get("variables") or ""
        mod = module_name(folder)
        by_module.setdefault(mod, []).append(
            {
                "kind": kind,
                "op_name": op_name,
                "sig": sig,
                "query": query,
                "example": example.strip(),
                "folder": folder,
            }
        )
    for ops in by_module.values():
        ops.sort(key=lambda o: (o["kind"] != "query", o["op_name"]))
    return dict(sorted(by_module.items()))


_HEADER = '''"""GreyMatter MCP tools for domain: {folder}.

GENERATED by scripts/generate_from_collection.py — do not edit by hand.
Regenerate via: python scripts/generate_from_collection.py
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from .._common import execute_operation

_DOC: dict[str, str] = {ALLDOCS}


def register(mcp: FastMCP, *, read_only: bool) -> None:
'''


def _example_snippet(example: str) -> str:
    if not example:
        return ""
    try:
        obj = json.loads(example)
    except (ValueError, TypeError):
        return ""
    compact = json.dumps(obj, separators=(",", ":"))
    if len(compact) > 300:
        compact = compact[:297] + "..."
    return compact


def _emit_tool(op: dict) -> str:
    name = tool_name(op["op_name"])
    decls = parse_variable_decls(op["sig"])
    example = _example_snippet(op["example"])
    base = OVERRIDES.get(op["op_name"]) or f"{op['folder']} · {op['kind']} {op['op_name']}."
    desc = base
    if decls:
        desc += " Variables: " + ", ".join(d[0] for d in decls) + "."
    if example:
        desc += f" Example variables: {example}"

    params: list[str] = []
    var_items: list[str] = []
    ordered = sorted(decls, key=lambda d: not d[2])
    for var_name, gql_type, required in ordered:
        annot = py_annotation(gql_type)
        pdesc = f"GraphQL: {gql_type}"
        if required:
            params.append(
                f"        {var_name}: Annotated[{annot}, Field(description={json.dumps(pdesc)})],"
            )
        else:
            params.append(
                f"        {var_name}: Annotated[{annot}, Field(default=None, description={json.dumps(pdesc)})] = None,"
            )
        var_items.append(f"{json.dumps(var_name)}: {var_name}")
    params.append(
        '        customer_slug: Annotated[str | None, Field(default=None, '
        'description="Override the x-reliaquest-customer (OpCo) header.")] = None,'
    )
    var_dict = "{" + ", ".join(var_items) + "}"
    indent = "    " if op["kind"] == "mutation" else ""

    body = f'''{indent}    @mcp.tool(name={json.dumps(name)}, description={json.dumps(desc)})
{indent}    async def {name}(
{chr(10).join((indent + p) for p in params)}
{indent}    ) -> Any:
{indent}        return await execute_operation(_DOC[{json.dumps(op["op_name"])}], {var_dict}, customer_slug=customer_slug)
'''
    return body


def _emit_module(folder: str, ops: list[dict]) -> str:
    docs = {op["op_name"]: op["query"] for op in ops}
    alldocs = "{\n" + "\n".join(
        f"    {json.dumps(k)}: {json.dumps(v)}," for k, v in docs.items()
    ) + "\n}"
    safe_folder = folder.replace("\\", "\\\\").replace('"', '\\"')
    out = _HEADER.replace("{folder}", safe_folder).replace("{ALLDOCS}", alldocs)

    queries = [o for o in ops if o["kind"] == "query"]
    mutations = [o for o in ops if o["kind"] == "mutation"]

    if not queries and not mutations:
        out += "    return\n"
        return out

    for op in queries:
        out += _emit_tool(op) + "\n"
    if mutations:
        out += "    if not read_only:\n"
        for op in mutations:
            out += _emit_tool(op) + "\n"
    return out


def generate(
    collection_path: Path = DEFAULT_COLLECTION,
    out_dir: Path = DEFAULT_OUT_DIR,
    endpoints_doc: Path = DEFAULT_DOC,
) -> None:
    collection = json.loads(Path(collection_path).read_text(encoding="utf-8"))
    by_module = _collect(collection)

    for mod, ops in by_module.items():
        seen_ops: dict[str, bool] = {}
        seen_tools: dict[str, str] = {}
        for op in ops:
            if op["op_name"] in seen_ops:
                raise ValueError(
                    f"Duplicate GraphQL operation name {op['op_name']!r} in module {mod!r}; "
                    "cannot generate unambiguous tools."
                )
            seen_ops[op["op_name"]] = True
            tn = tool_name(op["op_name"])
            if tn in seen_tools:
                raise ValueError(
                    f"Tool-name collision {tn!r} in module {mod!r} from operations "
                    f"{seen_tools[tn]!r} and {op['op_name']!r}."
                )
            seen_tools[tn] = op["op_name"]

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.py"):
        old.unlink()

    for mod, ops in by_module.items():
        (out_dir / f"{mod}.py").write_text(_emit_module(ops[0]["folder"], ops), encoding="utf-8")

    mod_names = list(by_module.keys())
    init_lines = [
        '"""Generated GreyMatter tool modules. Do not edit by hand."""',
        "",
        "from . import (",
        *[f"    {m}," for m in mod_names],
        ")",
        "",
        "GENERATED_MODULES = [",
        *[f"    {m}," for m in mod_names],
        "]",
        "",
    ]
    (out_dir / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")

    endpoints_doc.parent.mkdir(parents=True, exist_ok=True)
    doc_lines = ["# GreyMatter MCP — Tool Catalog", "",
                 "Generated from the Postman collection. Do not edit by hand.", ""]
    total = 0
    for mod, ops in by_module.items():
        doc_lines.append(f"## {ops[0]['folder']} (`{mod}.py`)")
        doc_lines.append("")
        doc_lines.append("| Tool | Kind | GraphQL operation |")
        doc_lines.append("|---|---|---|")
        for op in ops:
            total += 1
            doc_lines.append(f"| `{tool_name(op['op_name'])}` | {op['kind']} | `{op['op_name']}` |")
        doc_lines.append("")
    doc_lines.insert(4, f"**Total operations:** {total}\n")
    endpoints_doc.write_text("\n".join(doc_lines), encoding="utf-8")

    print(f"Generated {total} tools across {len(by_module)} modules into {out_dir}")


def main(argv: list[str]) -> int:
    collection = Path(argv[1]) if len(argv) > 1 else DEFAULT_COLLECTION
    if not collection.exists():
        print(f"Collection not found: {collection}", file=sys.stderr)
        return 2
    generate(collection_path=collection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
