# Remediation plan — greymatter-mcp

Fixes from a code review of this repository, ordered by priority. Tasks 1–4 are
mechanical and self-contained; follow them exactly. Task 0 is **maintainer-only**
— do **not** attempt it as an automated agent.

## Ground rules

- Work on a feature branch, one commit per task, descriptive commit messages.
- After every task, both of these must pass from the repo root:
  ```bash
  uv run pytest -q        # or: .venv/bin/pytest -q
  uv run ruff check .
  ```
- Files under `src/greymatter_mcp/tools/_generated/` are generated. Do not
  hand-edit them **except** for the single mechanical regex replacement in
  Task 2, which must also be mirrored in the generator so regeneration
  preserves it.
- When all tasks are done: bump `version` in `pyproject.toml` from `0.1.4` to
  `0.1.5` and add a `0.1.5` section to `CHANGELOG.md` summarizing Tasks 1–4.

---

## Task 0 — Git history cleanup (MAINTAINER ONLY — skip if you are an automated agent)

This task involves rewriting repository history with `git filter-repo` and
force-pushing. The specifics (which paths, which commits, and the exact
commands) were delivered to the maintainer privately and are intentionally not
listed here. Automated agents must not attempt any history rewrite or force
push.

---

## Task 1 — Stop retrying mutations (duplicate-side-effect bug)

**Problem.** `GreyMatterClient.execute` in `src/greymatter_mcp/client.py`
retries on network errors and on HTTP 429/500/502/503/504 for *every*
operation, including mutations (`create_user`, `create_api_key`,
`add_incident_comment`, `run_playbook`, …). If a mutation succeeds server-side
but the response is lost (read timeout, gateway 502), the retry executes the
mutation a second time — duplicate comments, duplicate API keys, a playbook
run twice. Mutations must be sent exactly once.

**Fix — three edits:**

### 1a. Move `is_mutation_document` from `tools/graphql.py` to `tools/_common.py`

Cut the entire `is_mutation_document` function (and its docstring) out of
`src/greymatter_mcp/tools/graphql.py` and paste it into
`src/greymatter_mcp/tools/_common.py`. Add `import re` to `_common.py`'s
imports. Then in `graphql.py`, import it from its new home so all existing
references and tests keep working:

```python
from ._common import execute_operation, is_mutation_document
```

(`graphql.py` no longer needs its own `import re` if nothing else uses it —
remove the unused import so ruff passes. Note Task 3 rewrites this function;
if doing both tasks, move it first, then apply Task 3's rewrite in
`_common.py`.)

### 1b. Add a `retryable` flag to `GreyMatterClient.execute` in `src/greymatter_mcp/client.py`

Change the signature:

```python
    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        customer_slug: str | None = None,
        retryable: bool = True,
    ) -> Any:
```

Inside the retry loop, change the network-error branch from:

```python
                if attempt == _MAX_RETRIES - 1:
                    raise GreyMatterAPIError(0, f"Network error: {e}") from e
```

to:

```python
                if not retryable or attempt == _MAX_RETRIES - 1:
                    raise GreyMatterAPIError(0, f"Network error: {e}") from e
```

and change the retryable-status branch from:

```python
            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
```

to:

```python
            if (
                retryable
                and response.status_code in _RETRYABLE_STATUS_CODES
                and attempt < _MAX_RETRIES - 1
            ):
```

With `retryable=False`, a 429/5xx now falls through to the existing
`status_code >= 400` hard-failure branch on the first attempt. Update the
`execute` docstring to document the new parameter (mutations are sent exactly
once because they are not idempotent).

### 1c. Set the flag in `execute_operation` in `src/greymatter_mcp/tools/_common.py`

Every tool (generated tools and the `graphql_query` escape hatch) goes through
`execute_operation`, so this one call site covers everything:

```python
    client = await get_client()
    cleaned = {k: coerce_json(v) for k, v in drop_none(variables or {}).items()}
    return await client.execute(
        query,
        cleaned,
        customer_slug=customer_slug,
        retryable=not is_mutation_document(query),
    )
```

### 1d. Tests

Add to `tests/test_client.py`, following the existing pytest-httpx patterns in
that file (mocked responses, no live calls):

- A **mutation** document (e.g. `"mutation m { x }"`) that gets a 502: assert
  exactly **one** request was sent and `GreyMatterAPIError` is raised
  (call `execute(..., retryable=False)` — or go through `execute_operation`).
- A **query** document that gets a 502 then a 200: assert it retried and
  returned the data (this likely already exists; keep it passing).
- A mutation that hits a network error (`httpx.ConnectError`): assert no retry
  (one request attempt, immediate `GreyMatterAPIError`).

---

## Task 2 — Fix wrong variable type `RoleFilter` → `RoleOrder` in generated documents

**Problem.** ~25 generated GraphQL documents declare an order variable with a
filter type, e.g. `$order3: RoleFilter`, then use it as the `order:` argument
of a `roles(...)` connection. The schema's type for that argument is
`RoleOrder`. Servers that enforce variable-usage validation reject the whole
document on every call. The typo comes from the vendor Postman collection, so
the durable fix lives in the generator.

**Fix:**

### 2a. Mechanical fix to the generated files

```bash
cd src/greymatter_mcp/tools/_generated
sed -i -E 's/(\$order[0-9]*): RoleFilter/\1: RoleOrder/g' *.py
```

This must change occurrences in: `api_keys.py`, `tasks.py`,
`reference_lists.py`, `emergency_contacts.py`, `user.py`, `incidents.py`,
`discover_tasks.py`, `cases.py`, `playbooks.py`, `drp_alerts.py`. It edits
only the type name inside the `_DOC` GraphQL strings — nothing else.

Also fix the matching Python parameter descriptions in the same files: any
generated tool parameter named `order`/`orderN` whose `Field(description=...)`
says `"GraphQL: RoleFilter"` should now say `"GraphQL: RoleOrder"`:

```bash
# Only lines for order parameters, not filter parameters:
sed -i -E 's/(order[0-9]*: Annotated\[Any \| None, Field\(default=None, description="GraphQL: )RoleFilter(")/\1RoleOrder\2/g' *.py
```

### 2b. Mirror the fix in the generator

In `scripts/generate_from_collection.py`, add near the other module-level maps
(e.g. after `_SCALAR_ANNOT`):

```python
# Corrections for known typos in the vendor collection's documents. Applied to
# every GraphQL document (and to the derived per-variable type strings) before
# emission. Currently: order-by variables mistyped as RoleFilter must be
# RoleOrder to pass server-side variable-usage validation.
_TYPE_CORRECTIONS = [
    (re.compile(r"(\$order\d*)\s*:\s*RoleFilter\b"), r"\1: RoleOrder"),
]
```

Then find where each request's GraphQL document string is finalized (the value
that ends up in `_DOC`) and apply:

```python
for pattern, replacement in _TYPE_CORRECTIONS:
    document = pattern.sub(replacement, document)
```

Important: the generator also derives each tool parameter's annotation and
`"GraphQL: <Type>"` description from the document's variable declarations.
Apply the correction **before** variables are parsed out of the document, so
the descriptions come out as `RoleOrder` automatically.

### 2c. Regression test

Add a new file `tests/test_generated_documents.py`:

```python
"""Guards against known vendor-collection typos resurfacing in generated documents."""

import re

from greymatter_mcp.tools._generated import GENERATED_MODULES


def test_no_order_variable_declared_with_a_filter_type():
    # An $order/$orderN variable typed as a *Filter input is a collection typo
    # (e.g. RoleFilter where the schema expects RoleOrder) and breaks
    # server-side variable-usage validation for the whole document.
    for module in GENERATED_MODULES:
        for op_name, document in module._DOC.items():
            match = re.search(r"\$order\d*\s*:\s*\w*Filter\b", document)
            assert match is None, f"{module.__name__}.{op_name}: {match.group(0)}"
```

(If `GENERATED_MODULES` does not exist under that name, check
`src/greymatter_mcp/tools/_generated/__init__.py` for the actual export and
adapt.)

### 2d. Note for the maintainer (put this in the PR description)

The fix was verified against the schema's `RoleOrder` input type, but the live
API was not called. Maintainer should run one `incident` query with an
`order3` value against the live API to confirm.

---

## Task 3 — Close the multi-operation read-only bypass in `is_mutation_document`

**Problem.** The scanner returns `False` as soon as it sees a leading `query`
keyword, so a document like `query a { x } mutation b { y }` is classified as
a query. The client never sends `operationName`, so a spec-compliant server
rejects multi-operation documents anyway — but a lenient server could execute
the mutation, defeating read-only mode. Scan **all** operations instead of
just the first.

**Fix.** Replace the body of `is_mutation_document` (after Task 1a it lives in
`src/greymatter_mcp/tools/_common.py`) with the following. Keep the existing
docstring, but update it to say the scanner now checks every operation in the
document, not just the leading one:

```python
def is_mutation_document(query: str) -> bool:
    # (keep/adapt the existing docstring)
    text = query.lstrip("﻿")
    text = re.sub(r"#[^\n]*", "", text)
    text = text.strip()
    n = len(text)

    def skip_braced_block(start: int) -> int:
        """Return the index just past the {...} block found at/after start, or -1."""
        brace = text.find("{", start)
        if brace == -1:
            return -1
        depth, j = 0, brace
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return -1

    i = 0
    parse_failed = False
    while i < n:
        # Whitespace and commas are insignificant separators in GraphQL.
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] == "{":
            # Anonymous query shorthand — a query; skip its body, keep scanning.
            nxt = skip_braced_block(i)
            if nxt == -1:
                parse_failed = True
                break
            i = nxt
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if not m:
            i += 1
            continue
        word = m.group(0)
        if word == "mutation":
            return True
        if word in ("query", "subscription", "fragment"):
            # A non-mutation definition: skip its entire body and KEEP
            # scanning — a mutation may legally follow in the same document.
            nxt = skip_braced_block(i)
            if nxt == -1:
                parse_failed = True
                break
            i = nxt
            continue
        i += len(word)

    if parse_failed:
        # Couldn't scan structurally — be conservative: any "mutation" word
        # anywhere means we treat the document as a mutation.
        return bool(re.search(r"\bmutation\b", text))
    return False
```

**Tests.** Add to `tests/test_graphql_tool.py` (match the existing test style;
they call `is_mutation_document` directly — keep importing it from
`greymatter_mcp.tools.graphql`, which re-exports it after Task 1a):

```python
def test_trailing_mutation_in_multi_operation_document_is_detected():
    assert is_mutation_document("query a { x } mutation b { y }")


def test_multiple_query_operations_are_not_a_mutation():
    assert not is_mutation_document("query a { x } query b { y }")


def test_fragment_then_query_then_mutation_is_detected():
    assert is_mutation_document(
        "fragment f on T { x } query a { ...f } mutation b { y }"
    )
```

All existing tests for this function must still pass unchanged.

---

## Task 4 — Minor hardening (one commit, four small edits)

### 4a. Validate `LOG_LEVEL` in `src/greymatter_mcp/config.py`

In `Config.from_env`, replace:

```python
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
```

with:

```python
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            raise ConfigError(
                f"LOG_LEVEL must be a standard logging level name (got {log_level!r})"
            )
```

Add a test to `tests/test_config.py`: setting `LOG_LEVEL=verbose` raises
`ConfigError` (use the existing env-patching + `reset_config_cache()` pattern
in that file).

### 4b. Widen the shutdown exception guard in `src/greymatter_mcp/server.py`

In `main()`'s `finally` block, the httpx client being closed was created on an
event loop that is already gone, and `aclose()` can raise more than
`RuntimeError` (e.g. anyio errors). Change:

```python
        try:
            asyncio.run(shutdown_client())
        except RuntimeError:
            pass
```

to:

```python
        try:
            asyncio.run(shutdown_client())
        except Exception:  # noqa: BLE001 — best-effort cleanup; process is exiting
            pass
```

Keep the surrounding comments; adjust the one that mentions `RuntimeError`.

### 4c. Verify tag ↔ version in `.github/workflows/release.yml`

In the `build` job, insert this step between the checkout and setup-python
steps (after checkout):

```yaml
      - name: Verify tag matches pyproject version
        run: |
          python3 - <<'EOF'
          import os, tomllib
          with open("pyproject.toml", "rb") as f:
              version = tomllib.load(f)["project"]["version"]
          tag = os.environ["GITHUB_REF_NAME"].removeprefix("v")
          assert tag == version, f"tag v{tag} != pyproject version {version}"
          EOF
```

(Note: this step must come after `actions/setup-python@v5` if the runner's
default python3 is older than 3.11 — `tomllib` requires 3.11+. Placing it
after the existing setup-python step is safest.)

### 4d. README install-note consistency

In `README.md`, the Quick start shows `uv tool install greymatter-mcp` /
`pip install greymatter-mcp` followed by a note that PyPI publishing is
pending. If the package **is** now live on PyPI, delete the note. If not,
move the note *above* the install commands so readers see it first. Do not
change anything else in the README.

---

## Final checklist

- [ ] `uv run pytest -q` — all tests pass, including the new ones from Tasks 1–4
- [ ] `uv run ruff check .` — clean
- [ ] Generated files changed **only** by the Task 2 regexes; generator updated to match
- [ ] `pyproject.toml` version is `0.1.5`; `CHANGELOG.md` has a matching entry
- [ ] Task 0 was **not** attempted (maintainer-only)
