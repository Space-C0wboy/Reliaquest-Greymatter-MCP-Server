"""Generate FastMCP tool modules from the GreyMatter Postman collection.

This MCP server exposes the ReliaQuest GreyMatter GraphQL API to MCP clients as a
set of typed tools. Rather than hand-write a tool function for every endpoint, we
treat the vendor's Postman collection (which already contains a working GraphQL
document + example variables for each request) as the source of truth and *generate*
one FastMCP tool module per domain folder from it.

What this script produces, given the collection:
  - src/greymatter_mcp/tools/_generated/<domain>.py — one module per Postman top-level
    folder ("Incidents", "Tasks", ...), each exposing a `register(mcp, *, read_only)`
    that wires up that domain's tools.
  - src/greymatter_mcp/tools/_generated/__init__.py — imports every module and lists
    them in GENERATED_MODULES so the server can register them all in one pass.
  - docs/ENDPOINTS.md — a human-readable catalog table of every generated tool.

The companion script scripts/introspect.py fetches the *live* schema by introspection;
that is used to verify the documents this generator emits actually match the server.

Usage:
    python scripts/generate_from_collection.py [COLLECTION_JSON]

Defaults to "Development Reference/GreyMatter API.postman_collection.json".
Writes src/greymatter_mcp/tools/_generated/<domain>.py, _generated/__init__.py,
and docs/ENDPOINTS.md.

Determinism matters: the same collection must always yield byte-identical output so
the generated files can be checked into git and reviewed in diffs. We achieve this by
sorting modules and operations into a fixed order and writing files with explicit LF
newlines (see `generate`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Default input/output locations, all relative to the repo root (the CWD the script
# is expected to run from). main() lets the collection path be overridden on argv.
DEFAULT_COLLECTION = Path("Development Reference/GreyMatter API.postman_collection.json")
DEFAULT_OUT_DIR = Path("src/greymatter_mcp/tools/_generated")
DEFAULT_DOC = Path("docs/ENDPOINTS.md")

# Maps a GraphQL *scalar* type name to the Python annotation we put on the generated
# tool parameter. Anything not in this map (input objects, enums, custom scalars) is
# treated as `Any` by py_annotation() — we don't have the full schema here, only the
# variable declarations from each Postman document, so non-scalars stay loosely typed.
_SCALAR_ANNOT = {
    "String": "str",
    "ID": "str",
    "Int": "int",
    "Float": "float",
    "Boolean": "bool",
}

# Richer, hand-curated descriptions for high-traffic SOC operations. Keyed by GraphQL
# operation name. The default tool description is just "<folder> · <kind> <op>"; for the
# operations an analyst reaches for most (incidents, cases, tasks, ...) that is too terse,
# so we override it with text that spells out the relevant input shape and the legal enum
# values (states, close codes, ...). _emit_tool consults this map by op_name; only the
# description text is overridden — parameters/signature are always derived from the
# document. Enum values below come from the GreyMatter API documentation.
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
    "cases": "List cases (with nested activity/children/comments connections). The OUTER list page size is `first3` (set it to bound results, e.g. first3=25); `first`/`first1`/`first2` page the nested connections.",
    "createCase": "Create a case. NOTE: `state` is effectively REQUIRED despite being schema-optional — omitting it makes the GreyMatter API return success=false with no error. Always pass `state` (e.g. NEW). `type` is required (GENERAL, DISCOVER_EXPOSURE, TEAMMATE); `severity` optional (INFORMATIONAL..CRITICAL).",
}

# Minimal response selections for mutations whose vendor selection set is so heavy the
# round-trip can exceed the MCP client timeout (issue #1). The Postman documents for some
# mutations ask the server to echo back the entire (huge) incident/task object; we only
# need a confirmation, so we swap in a tiny selection set instead.
#
# Keyed by GraphQL operation name; the value is the *replacement* selection set (braces
# included) that _set_mutation_selection splices in for the root mutation field's `{...}`.
# Important interaction: replacing a fat selection with a slim one can leave variables that
# only the old fields referenced declared-but-unused; that would make the document invalid.
# _collect runs _prune_unused_variables *after* this trim so those orphaned variables (and
# the matching tool parameters) drop out automatically. This map works hand-in-hand with
# _prune_unused_variables — don't apply one without the other.
MUTATION_RESPONSE_TRIMS: dict[str, str] = {
    "retainIncident": "{ incident { id retained state } success }",
    "releaseIncident": "{ incident { id retained state } success }",
    "unresolveIncident": "{ incident { id state } success }",
    "updateTaskRetainedStatus": "{ success task { id retained state } }",
}

# Server-side-bug workarounds: drop specific field selections from a given operation's
# GraphQL document because the GreyMatter API errors out when they are requested. Keyed by
# operation name -> list of field names to remove
# from that operation's document. _collect applies this *first* in its pipeline (before the
# mutation trim and the variable prune), using _strip_field_selection to cut each named
# field plus its sub-selection. The dropped data isn't lost to users — it remains fetchable
# through the graphql_query escape-hatch tool; we just can't bake it into the canned query.
FIELD_EXCLUSIONS: dict[str, list[str]] = {
    "case": ["discoverExposure"],
    "cases": ["discoverExposure"],
    "playbooks": ["supportedTechnologies"],
}

# Per-field human-readable fragment used when _emit_tool appends the "this field was
# omitted as a workaround" note to a tool's description. Keyed by the same field names as
# FIELD_EXCLUSIONS; the value is how that field should read in prose (backtick-quoted).
# If a field is excluded but missing here, _emit_tool falls back to `<field>` formatting.
_EXCLUSION_NOTES: dict[str, str] = {
    "discoverExposure": "`discoverExposure`",
    "supportedTechnologies": "`supportedTechnologies`",
}

# Matches the opening of a GraphQL document: the operation keyword, an optional operation
# name, and an optional variable-declaration block. Capture groups are:
#   1 = kind ("query" | "mutation")
#   2 = operation name (may be absent for anonymous operations)
#   3 = the "(...)" variable signature (may be absent when there are no variables)
# DOTALL lets the signature span multiple lines. NOTE: group 3 uses "[^)]*" so it stops at
# the first ")" — fine here because GraphQL variable type refs never contain a literal
# parenthesis (lists/non-null use [] and !), so the signature is always paren-free inside.
_OP_RE = re.compile(r"^\s*(query|mutation)\s+([A-Za-z0-9_]+)?\s*(\([^)]*\))?", re.DOTALL)


def parse_operation(query: str) -> tuple[str, str, str]:
    """Pull the operation kind, name, and variable signature out of a GraphQL document.

    Args:
        query: A full GraphQL document string (e.g. "query incidents($first: Int) {...}").

    Returns:
        (kind, operation_name, signature) where kind is "query"/"mutation", name is the
        operation name (e.g. "incidents"), and signature is the raw "(...)" variable block
        including its parentheses (empty string when there are no variables).

    Why: callers need the op name to key into OVERRIDES/_DOC and need the signature so
    parse_variable_decls can turn it into typed tool parameters.

    Gotcha: if the document doesn't match _OP_RE at all (malformed/unexpected), we return a
    benign ("query", "", "") default rather than raising — _collect then skips it because
    the empty op name fails the "if not op_name" guard.
    """
    m = _OP_RE.match(query)
    if not m:
        return ("query", "", "")
    kind = m.group(1)
    name = m.group(2) or ""   # anonymous operations have no name -> ""
    sig = m.group(3) or ""    # no variables -> "" (parse_variable_decls returns [])
    return (kind, name, sig)


def parse_variable_decls(signature: str) -> list[tuple[str, str, bool]]:
    """Parse a variable signature into a list of (name, gql_type, required) tuples.

    Args:
        signature: The "(...)" block from parse_operation, e.g. "($a: String, $b: Foo!)".
            The surrounding parentheses are optional/tolerated.

    Returns:
        One tuple per variable: the name with its leading "$" stripped, the GraphQL type
        as written (keeping the trailing "!" / "[]" so py_annotation can interpret it),
        and a `required` bool that is True when the type ends in "!".

    Why: this is the bridge from GraphQL variable declarations to the typed Python tool
    parameters _emit_tool generates. Splitting on "," is safe because, like _OP_RE above,
    GraphQL variable type refs never contain a comma (lists are "[T]", not "T,T").
    """
    inner = signature.strip()
    # Tolerate being handed the signature with or without its wrapping parentheses.
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
        # Skip empties (e.g. trailing comma) and anything without a "name: type" colon.
        if not part or ":" not in part:
            continue
        name_part, type_part = part.split(":", 1)
        name = name_part.strip().lstrip("$")     # "$first" -> "first"
        gql_type = type_part.strip()
        required = gql_type.endswith("!")        # GraphQL non-null marker => required
        out.append((name, gql_type, required))
    return out


def py_annotation(gql_type: str) -> str:
    """Map a GraphQL type to the Python annotation string used in a tool's signature.

    Args:
        gql_type: The GraphQL type as written in the document, e.g. "String", "ID!",
            "IncidentFilter", or "[ID!]!".

    Returns:
        A Python annotation string. Required (non-null) types map to the bare type; nullable
        types get "| None" so the parameter can default to None. Mapping rules:
          - List types ("[...]") -> "list" (we don't model element types here).
          - Known scalars -> their Python equivalent ("str"/"int"/"float"/"bool").
          - Everything else (input objects, enums, custom scalars) -> "Any", because we only
            have the document, not the schema, so we can't name a precise type.

    Gotcha: lists collapse to plain "list" with no "| None", matching how FastMCP/pydantic
    treat them; required-ness of a list is conveyed by whether _emit_tool gives it a default.
    """
    t = gql_type.strip()
    if t.startswith("["):
        return "list"             # list types are left untyped at element level
    base = t.rstrip("!")          # strip the non-null marker to look up the base scalar
    required = t.endswith("!")
    if base in _SCALAR_ANNOT:
        py = _SCALAR_ANNOT[base]
        return py if required else f"{py} | None"   # nullable scalar gets an Optional
    return "Any" if required else "Any | None"       # unknown type -> Any (optionally None)


def _strip_field_selection(query: str, field_name: str) -> str:
    """Remove every selection of `field_name` (and its `{...}` sub-block, if it has one).

    Args:
        query: The GraphQL document to edit.
        field_name: The field to excise wherever it appears as a selection.

    Returns:
        The document with all selections of `field_name` removed.

    Why: used to apply FIELD_EXCLUSIONS — some fields trigger server-side errors, so we cut
    them from the canned document. A field can be either a scalar ("supportedTechnologies")
    or an object with a sub-selection ("discoverExposure { id name }"); we handle both.

    Gotchas:
      - The lookbehind/lookahead "(?<![A-Za-z0-9_])...(?![A-Za-z0-9_])" matches the name only
        as a *whole identifier*, so "discoverExposure" never clips "discoverExposureSummary"
        and never touches an argument/variable name that merely contains the substring.
      - We use manual brace-matching (counting "{"/"}" depth) rather than a regex because
        selection sets nest arbitrarily; a regex can't reliably find the matching close brace.
      - The loop repeats until no match remains, so repeated occurrences are all removed.
    """
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(field_name) + r"(?![A-Za-z0-9_])")
    while True:
        m = pattern.search(query)
        if not m:
            return query   # no more occurrences -> done
        start, j = m.start(), m.end()
        # Skip any whitespace between the field name and a possible "{" sub-selection.
        while j < len(query) and query[j] in " \t\r\n":
            j += 1
        if j < len(query) and query[j] == "{":
            # Object field: find the matching close brace by tracking nesting depth, then
            # delete the field name *and* its whole "{...}" block.
            depth, k = 0, j
            while k < len(query):
                if query[k] == "{":
                    depth += 1
                elif query[k] == "}":
                    depth -= 1
                    if depth == 0:
                        k += 1
                        break
                k += 1
            query = query[:start] + query[k:]
        else:
            # Scalar field: nothing to brace-match, just drop the identifier itself.
            query = query[:start] + query[j:]


def _prune_unused_variables(query: str) -> str:
    """Drop variable declarations that are no longer referenced in the operation body.

    Args:
        query: The GraphQL document, possibly after fields were stripped or a mutation
            selection was trimmed.

    Returns:
        The document with any orphaned "$var: Type" declarations removed from the signature
        (the body is untouched). Unchanged if every declared variable is still used.

    Why: stripping a field (FIELD_EXCLUSIONS) or swapping a mutation's selection
    (MUTATION_RESPONSE_TRIMS) can leave variables declared in the signature that nothing
    references anymore. GraphQL rejects a document with declared-but-unused variables, so we
    must remove them — and _emit_tool keys its parameters off the (re-parsed) signature, so
    pruning here is also what keeps the tool's parameter list honest.
    """
    m = _OP_RE.match(query)
    if not m or not m.group(3):
        return query   # no signature at all -> nothing to prune
    sig = m.group(3)
    sig_start, sig_end = m.start(3), m.end(3)
    body = query[sig_end:]   # everything after the signature is where variables get used
    decls = parse_variable_decls(sig)
    if not decls:
        return query
    # Keep only the variables actually referenced (as "$name", whole-identifier) in the body.
    used = [
        (name, gql_type)
        for name, gql_type, _req in decls
        if re.search(r"(?<![A-Za-z0-9_])\$" + re.escape(name) + r"(?![A-Za-z0-9_])", body)
    ]
    if len(used) == len(decls):
        return query   # all variables used -> leave the document byte-for-byte unchanged
    # Rebuild the signature from the survivors; if none remain, drop the "(...)" entirely.
    new_sig = ("(" + ", ".join(f"${n}: {t}" for n, t in used) + ")") if used else ""
    return query[:sig_start] + new_sig + query[sig_end:]


def _set_mutation_selection(query: str, op_name: str, selection: str) -> str:
    """Replace the selection set of the root mutation field `op_name` with `selection`.

    Args:
        query: The mutation document.
        op_name: The mutation field name (same as the operation name for these docs).
        selection: The replacement selection set, braces included, e.g. "{ success }".

    Returns:
        The document with the root field's "{...}" swapped for `selection`. Returned
        unchanged if the field invocation can't be located.

    Why: implements MUTATION_RESPONSE_TRIMS — collapse a huge response selection down to a
    minimal confirmation so the round-trip stays under the client timeout.

    The subtlety — skipping the operation-name occurrence: in "mutation retainIncident(...)
    { retainIncident(...) { ... } }" the name appears twice: once as the *operation name*
    and once as the *root field invocation*. We must rewrite only the field invocation; if
    we matched the operation-name occurrence we'd treat the whole operation body as the
    selection and replace everything. So for each whole-word match we look at the text
    immediately before it: if it's "mutation "/"query " then this is the operation-name
    occurrence and we skip it. Args and the selection block are located with manual
    paren/brace depth-matching (same reasoning as _strip_field_selection).
    """
    for mt in re.finditer(r"(?<![A-Za-z0-9_])" + re.escape(op_name) + r"(?![A-Za-z0-9_])", query):
        # Skip the operation-name occurrence (e.g. "mutation retainIncident") so we
        # only ever rewrite the *field invocation*; otherwise we'd replace the whole
        # operation body when the operation and root field share a name.
        if re.search(r"(?:mutation|query)\s+$", query[: mt.start()]):
            continue
        i, n = mt.end(), len(query)
        # Step over whitespace after the field name.
        while i < n and query[i] in " \t\r\n":
            i += 1
        if i < n and query[i] == "(":  # the field has an args block — skip past it (balanced)
            depth = 0
            while i < n:
                if query[i] == "(":
                    depth += 1
                elif query[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            # ...and any whitespace between the args and the "{".
            while i < n and query[i] in " \t\r\n":
                i += 1
        if i < n and query[i] == "{":  # found the selection block; find its matching close
            depth, j = 0, i
            while j < n:
                if query[j] == "{":
                    depth += 1
                elif query[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            # Splice: keep everything up to the "{", drop the old block, insert the new one.
            return query[:i] + selection + query[j:]
    return query   # field invocation not found -> leave the document unchanged


def tool_name(op_name: str) -> str:
    """Convert a camelCase/PascalCase GraphQL field name to a snake_case MCP tool name.

    Args:
        op_name: The GraphQL operation/field name, e.g. "acknowledgeIncident".

    Returns:
        The snake_case tool name, e.g. "acknowledge_incident". Already-snake names like
        "incidents" pass through unchanged.

    Why: MCP tool names are snake_case by convention. The two regexes insert an underscore
    before a capitalized word and at the lower/digit-to-upper boundary respectively, which
    together handle both "runPlaybook" -> "run_playbook" and acronym-ish transitions.
    """
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", op_name)   # "...Playbook" -> "..._Playbook"
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)        # "runP..." -> "run_P..."
    return s.lower()


def module_name(folder: str) -> str:
    """Convert a Postman domain folder name into a valid snake_case module filename stem.

    Args:
        folder: The top-level Postman folder name, e.g. "API Keys", "DRP Alerts".

    Returns:
        A snake_case Python-identifier-safe module name (no ".py"), e.g. "api_keys",
        "drp_alerts". Guaranteed to be a legal identifier that doesn't start with a digit.

    Why: each domain folder becomes a generated module that must be importable, so the name
    has to be a valid Python identifier. The steps below normalize separators, split
    camelCase, strip illegal characters, and finally guarantee a safe leading character.
    """
    s = folder.strip().replace("-", " ").replace("/", " ")  # treat - and / as word breaks
    s = re.sub(r"\s+", "_", s)                                # spaces -> underscores
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)              # split camelCase (as tool_name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^a-z0-9_]", "", s.lower())                  # drop anything not [a-z0-9_]
    s = re.sub(r"_+", "_", s).strip("_")                      # collapse/trim underscores
    if not s or s[0].isdigit():
        s = "mod_" + s   # ensure a valid identifier that doesn't lead with a digit
    return s


def _iter_requests(items, top_folder=None):
    """Recursively walk the Postman item tree, yielding GraphQL leaf requests.

    Args:
        items: A list of Postman items (folders have an "item" list; requests don't).
        top_folder: The name of the *top-level* folder this recursion descends from; set on
            the first level and carried down so every leaf is attributed to its domain.

    Yields:
        (top_folder, request_dict) for each leaf request whose body is a GraphQL query.

    Why: Postman collections nest folders arbitrarily, but we only care about which *top*
    folder a request lives under (that becomes its module). So we remember the top folder
    on the first descent (`top_folder or name`) and keep passing it down. Non-GraphQL
    requests (e.g. REST stubs) are filtered out here. "Misc" is the fallback bucket for a
    request that somehow has no enclosing folder.
    """
    for it in items or []:
        name = it.get("name", "")
        if "item" in it:
            # Folder node: recurse, fixing top_folder to the first folder name we saw.
            yield from _iter_requests(it["item"], top_folder or name)
        else:
            # Leaf node: only yield it if it actually carries a GraphQL query body.
            req = it.get("request") or {}
            body = req.get("body") or {}
            if body.get("mode") == "graphql" and body.get("graphql", {}).get("query"):
                yield (top_folder or "Misc", req)


def _collect(collection: dict) -> dict[str, list[dict]]:
    """Parse every GraphQL request in the collection into normalized per-module op records.

    Args:
        collection: The parsed Postman collection JSON.

    Returns:
        An ordered dict mapping module name -> list of operation dicts (each with kind,
        op_name, sig, query, example, folder). Both the dict and each list are sorted
        deterministically (see below).

    The per-operation pipeline (order matters!):
      1. Strip excluded fields (FIELD_EXCLUSIONS) from the document — must run first so the
         later prune can see which variables the removed fields left behind.
      2. For mutations, trim the heavy response selection (MUTATION_RESPONSE_TRIMS).
      3. Prune now-unused variable declarations left over from steps 1-2.
      4. Re-parse the (now-edited) document so `sig` reflects the pruned signature — the
         emitted tool parameters are derived from this final `sig`, not the original.

    Determinism: operations within a module are sorted queries-before-mutations and then by
    op_name (the key `(kind != "query", op_name)` puts queries first since False < True), and
    the modules themselves are returned in sorted key order. Same collection => same output.
    """
    by_module: dict[str, list[dict]] = {}
    for folder, req in _iter_requests(collection.get("item", [])):
        gql = req["body"]["graphql"]
        query = gql["query"].strip()
        kind, op_name, sig = parse_operation(query)
        if not op_name:
            continue   # anonymous/unparseable operation -> can't name a tool, skip it
        # --- per-operation transform pipeline (see docstring for why this order) ---
        for _excl in FIELD_EXCLUSIONS.get(op_name, []):
            query = _strip_field_selection(query, _excl)
        if kind == "mutation" and op_name in MUTATION_RESPONSE_TRIMS:
            query = _set_mutation_selection(query, op_name, MUTATION_RESPONSE_TRIMS[op_name])
        query = _prune_unused_variables(query)
        kind, op_name, sig = parse_operation(query)   # re-parse: sig now reflects pruning
        example = gql.get("variables") or ""           # Postman's example variables JSON
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
    # Deterministic intra-module order: queries first (False sorts before True), then by name.
    for ops in by_module.values():
        ops.sort(key=lambda o: (o["kind"] != "query", o["op_name"]))
    return dict(sorted(by_module.items()))   # deterministic module order


# Module template. _emit_module substitutes {folder} (the domain name) and {ALLDOCS}
# (the literal _DOC mapping) into this string, then appends the tool definitions emitted by
# _emit_tool. The docstring is written for someone *reading a generated file* (not this
# generator), so it explains how the module is wired rather than how it was produced.
_HEADER = '''"""GreyMatter MCP tools for domain: {folder}.

GENERATED by scripts/generate_from_collection.py — DO NOT EDIT BY HAND.
Any manual change here will be overwritten the next time the generator runs; to change a
tool, edit the generator (or the source Postman collection) and regenerate via:
    python scripts/generate_from_collection.py

How this module works:
  - `register(mcp, *, read_only)` is the entry point: the server calls it to register every
    tool in this domain onto the shared FastMCP instance.
  - `_DOC` maps each GraphQL operation name to its (possibly trimmed/pruned) GraphQL document
    string. Each tool below looks up its document in `_DOC` at call time.
  - Each generated tool is a thin async wrapper: it accepts typed parameters (one per GraphQL
    variable, plus an optional `customer_slug` header override) and forwards them as GraphQL
    variables to `execute_operation`, which performs the actual HTTP request.
  - Query tools are always registered. Mutation tools are registered ONLY when `read_only`
    is False, so a read-only deployment never exposes state-changing operations.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from .._common import execute_operation

# operation name -> GraphQL document string (after exclusions/trims/pruning were applied).
_DOC: dict[str, str] = {ALLDOCS}


def register(mcp: FastMCP, *, read_only: bool) -> None:
'''


def _example_snippet(example: str) -> str:
    """Turn Postman's example-variables JSON into a compact one-line snippet for a tool desc.

    Args:
        example: The raw "variables" string from the Postman request (may be empty or
            invalid JSON).

    Returns:
        A compact JSON string (no spaces) capped at 300 chars, or "" if there's nothing
        usable. The cap keeps tool descriptions from bloating when an example is huge.

    Why: showing a real example payload in the tool description helps the model fill in
    complex input objects correctly. We compact and truncate so it stays a single short line.
    """
    if not example:
        return ""
    try:
        obj = json.loads(example)
    except (ValueError, TypeError):
        return ""   # not valid JSON -> just omit the example rather than emitting garbage
    compact = json.dumps(obj, separators=(",", ":"))   # drop whitespace for compactness
    if len(compact) > 300:
        compact = compact[:297] + "..."                 # truncate overly long examples
    return compact


def _emit_tool(op: dict) -> str:
    """Render the Python source for one FastMCP tool from a collected operation record.

    Args:
        op: One operation dict from _collect (kind, op_name, sig, query, example, folder).

    Returns:
        A string of valid Python source: a single `# ...` comment line naming the operation,
        followed by an `@mcp.tool(...)`-decorated async function. Mutations are indented one
        extra level because _emit_module nests them inside an `if not read_only:` block.

    What it builds:
      - description: OVERRIDES text if present, else a default; with the variable names and a
        compact example appended, plus a workaround note for any excluded field.
      - parameters: one Annotated param per GraphQL variable (required ones first so Python's
        "no default after default" rule holds), plus a trailing optional `customer_slug`.
      - body: forwards the variables dict to execute_operation, keyed by op_name into _DOC.

    Safety: every interpolated string (name/desc/var names) is passed through json.dumps so
    quotes, backslashes, and newlines in folder names or examples can't break the emitted
    Python (see test_emitted_code_safe_with_special_chars).
    """
    name = tool_name(op["op_name"])
    decls = parse_variable_decls(op["sig"])
    example = _example_snippet(op["example"])
    # Description: prefer the curated OVERRIDES text; otherwise a terse "<folder> · <kind> <op>".
    base = OVERRIDES.get(op["op_name"]) or f"{op['folder']} · {op['kind']} {op['op_name']}."
    desc = base
    if decls:
        desc += " Variables: " + ", ".join(d[0] for d in decls) + "."
    if example:
        desc += f" Example variables: {example}"

    # If we stripped a field for this op (FIELD_EXCLUSIONS), tell the caller how to still get it.
    excluded = FIELD_EXCLUSIONS.get(op["op_name"], [])
    if excluded:
        fields = ", ".join(_EXCLUSION_NOTES.get(f, f"`{f}`") for f in excluded)
        desc += (f" NOTE: {fields} is omitted from this query as a workaround for a "
                 "GreyMatter server-side error; request it via graphql_query if you need it.")

    params: list[str] = []
    var_items: list[str] = []
    # Required params must precede optional ones in a Python signature; `not d[2]` sorts the
    # required (True) variables ahead of the optional (False) ones. Each variable becomes
    # both a typed parameter and an entry in the variables dict forwarded to GraphQL.
    ordered = sorted(decls, key=lambda d: not d[2])
    for var_name, gql_type, required in ordered:
        annot = py_annotation(gql_type)
        pdesc = f"GraphQL: {gql_type}"   # surface the exact GraphQL type to the caller
        if required:
            params.append(
                f"        {var_name}: Annotated[{annot}, Field(description={json.dumps(pdesc)})],"
            )
        else:
            params.append(
                f"        {var_name}: Annotated[{annot}, Field(default=None, description={json.dumps(pdesc)})] = None,"
            )
        var_items.append(f"{json.dumps(var_name)}: {var_name}")
    # Every tool gets an optional customer_slug to override the OpCo header for multi-tenant accounts.
    params.append(
        '        customer_slug: Annotated[str | None, Field(default=None, '
        'description="Override the x-reliaquest-customer (OpCo) header.")] = None,'
    )
    var_dict = "{" + ", ".join(var_items) + "}"
    # Mutations live inside the `if not read_only:` block, so they need one extra indent level.
    indent = "    " if op["kind"] == "mutation" else ""

    # Teaching comment emitted just above the tool, at the tool's own indent, naming the
    # GraphQL operation, its kind, and the resulting MCP tool name.
    op_comment = f'{indent}    # {op["op_name"]} ({op["kind"]}) — GraphQL operation, tool name "{name}"'

    body = f'''{op_comment}
{indent}    @mcp.tool(name={json.dumps(name)}, description={json.dumps(desc)})
{indent}    async def {name}(
{chr(10).join((indent + p) for p in params)}
{indent}    ) -> Any:
{indent}        return await execute_operation(_DOC[{json.dumps(op["op_name"])}], {var_dict}, customer_slug=customer_slug)
'''
    return body


def _emit_module(folder: str, ops: list[dict]) -> str:
    """Render the full source of one generated domain module.

    Args:
        folder: The Postman domain folder name (used in the header docstring).
        ops: The operations for this module, already sorted queries-before-mutations.

    Returns:
        Complete Python source: the _HEADER (with _DOC filled in) followed by the body of
        register() — the query tools, then (if any) the mutation tools nested inside an
        `if not read_only:` block. Section comments mark each group for readers.

    Notes:
      - `_DOC` is built as a literal dict mapping op_name -> document; json.dumps on both key
        and value keeps it valid even for documents containing quotes/newlines.
      - safe_folder escapes backslashes/quotes so a folder name can't terminate the docstring.
      - If a module somehow has no operations we emit a bare `return` so register() still
        compiles as a valid (no-op) function.
    """
    docs = {op["op_name"]: op["query"] for op in ops}
    alldocs = "{\n" + "\n".join(
        f"    {json.dumps(k)}: {json.dumps(v)}," for k, v in docs.items()
    ) + "\n}"
    # Escape so a folder name with a quote/backslash can't break out of the _HEADER docstring.
    safe_folder = folder.replace("\\", "\\\\").replace('"', '\\"')
    out = _HEADER.replace("{folder}", safe_folder).replace("{ALLDOCS}", alldocs)

    queries = [o for o in ops if o["kind"] == "query"]
    mutations = [o for o in ops if o["kind"] == "mutation"]

    if not queries and not mutations:
        out += "    return\n"   # empty domain -> register() is a valid no-op
        return out

    # Queries are always registered; a section comment (4-space indent, inside register())
    # introduces them, but only when there actually are queries.
    if queries:
        out += "    # --- Queries (always registered) ---\n"
    for op in queries:
        out += _emit_tool(op) + "\n"
    if mutations:
        out += "    if not read_only:\n"
        # Mutations note lives INSIDE the `if not read_only:` block, so it sits at 8 spaces.
        out += "        # --- Mutations (registered only when read_only is False) ---\n"
        for op in mutations:
            out += _emit_tool(op) + "\n"
    return out


def generate(
    collection_path: Path = DEFAULT_COLLECTION,
    out_dir: Path = DEFAULT_OUT_DIR,
    endpoints_doc: Path = DEFAULT_DOC,
) -> None:
    """Read the collection and (re)write all generated modules, __init__.py, and ENDPOINTS.md.

    Args:
        collection_path: Path to the Postman collection JSON.
        out_dir: Directory to write the generated `_generated/*.py` modules into.
        endpoints_doc: Path to the markdown tool catalog to (over)write.

    Raises:
        ValueError: if two operations in the same module share a GraphQL operation name, or if
            two distinct operations map to the same snake_case tool name. Either case would
            produce ambiguous/duplicate tools, so we fail loudly instead of emitting them.

    Side effects: deletes stale `*.py` in out_dir, then writes one module per domain plus the
    package __init__ and the docs catalog. All writes use newline="\\n" so output is identical
    across OSes (Windows wouldn't otherwise) — a prerequisite for the determinism guarantee.
    """
    collection = json.loads(Path(collection_path).read_text(encoding="utf-8"))
    by_module = _collect(collection)

    # Collision guards: validate the whole batch BEFORE writing anything, so a duplicate never
    # leaves a half-generated tree on disk.
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
            # Two different op names could snake-case to the same tool name — also fatal.
            if tn in seen_tools:
                raise ValueError(
                    f"Tool-name collision {tn!r} in module {mod!r} from operations "
                    f"{seen_tools[tn]!r} and {op['op_name']!r}."
                )
            seen_tools[tn] = op["op_name"]

    out_dir.mkdir(parents=True, exist_ok=True)
    # Clean stale modules first so a renamed/removed domain doesn't leave an orphan file behind.
    for old in out_dir.glob("*.py"):
        old.unlink()

    for mod, ops in by_module.items():
        # newline="\n": force LF on every platform so generated output is byte-stable.
        (out_dir / f"{mod}.py").write_text(
            _emit_module(ops[0]["folder"], ops), encoding="utf-8", newline="\n"
        )

    # Build the package __init__: import every module and expose them via GENERATED_MODULES,
    # which the server iterates over to call each module's register().
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
    (out_dir / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8", newline="\n")

    # Finally, regenerate the human-readable catalog table (docs/ENDPOINTS.md).
    endpoints_doc.parent.mkdir(parents=True, exist_ok=True)
    doc_lines = ["# GreyMatter MCP — Tool Catalog", "",
                 "Generated from the Postman collection. Do not edit by hand.", ""]
    total = 0   # running count of operations, used both in the doc header and the final print
    for mod, ops in by_module.items():
        doc_lines.append(f"## {ops[0]['folder']} (`{mod}.py`)")
        doc_lines.append("")
        doc_lines.append("| Tool | Kind | GraphQL operation |")
        doc_lines.append("|---|---|---|")
        for op in ops:
            total += 1
            doc_lines.append(f"| `{tool_name(op['op_name'])}` | {op['kind']} | `{op['op_name']}` |")
        doc_lines.append("")
    # Insert the total after the title/intro lines (index 4), now that we've counted them all.
    doc_lines.insert(4, f"**Total operations:** {total}\n")
    endpoints_doc.write_text("\n".join(doc_lines), encoding="utf-8", newline="\n")

    print(f"Generated {total} tools across {len(by_module)} modules into {out_dir}")


def main(argv: list[str]) -> int:
    """CLI entry point: optionally take a collection path on argv, then run generate().

    Args:
        argv: The process argv list; argv[1], if present, overrides the collection path.

    Returns:
        Process exit code: 2 if the collection file is missing, otherwise 0 on success.
    """
    collection = Path(argv[1]) if len(argv) > 1 else DEFAULT_COLLECTION
    if not collection.exists():
        print(f"Collection not found: {collection}", file=sys.stderr)
        return 2
    generate(collection_path=collection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
