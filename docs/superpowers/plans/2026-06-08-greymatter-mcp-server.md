# GreyMatter MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server exposing the ReliaQuest GreyMatter GraphQL API (~150 operations across 22 domains) as curated tools generated from the vendor's Postman collection, plus a generic `graphql_query` escape hatch and a read-only safety toggle.

**Architecture:** A FastMCP server over a single async GraphQL client (httpx). Tools are produced by a deterministic generator that reads the exported Postman collection, reuses each operation's GraphQL document verbatim, and parses variable declarations into typed tool parameters. Generated modules (one per domain) live in `src/greymatter_mcp/tools/_generated/`; a hand-written escape-hatch tool and the registration glue live alongside. Mutations are gated behind `GREYMATTER_READ_ONLY`.

**Tech Stack:** Python ≥3.10, FastMCP ≥2.0, httpx, pydantic v2, python-dotenv; pytest + pytest-httpx; ruff; hatchling. Matches the ThreatLocker / Checkpoint reference servers.

**Reference material (local, gitignored):** `Development Reference/GreyMatter API.postman_collection.json` and the four GreyMatter PDFs. The collection is the source of truth for generation.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Packaging (hatchling), deps, ruff/pytest config, `greymatter-mcp` entrypoint |
| `.env.example` | Documented env vars |
| `README.md`, `CHANGELOG.md`, `LICENSE` | Docs + MIT license |
| `src/greymatter_mcp/__init__.py` | Package marker, version |
| `src/greymatter_mcp/config.py` | Env-based `Config` dataclass + `get_config()` |
| `src/greymatter_mcp/errors.py` | `GreyMatterAPIError`, `GreyMatterGraphQLError` |
| `src/greymatter_mcp/client.py` | Async GraphQL client (retry/backoff, GraphQL-error handling) |
| `src/greymatter_mcp/server.py` | FastMCP entrypoint (`build_server`, `main`) |
| `src/greymatter_mcp/tools/__init__.py` | `register_all(mcp)` + read-only gating |
| `src/greymatter_mcp/tools/_common.py` | `execute_operation()` helper shared by generated tools |
| `src/greymatter_mcp/tools/graphql.py` | Hand-written `graphql_query` escape hatch |
| `src/greymatter_mcp/tools/_generated/__init__.py` | Generated module registry (`GENERATED_MODULES`) |
| `src/greymatter_mcp/tools/_generated/<domain>.py` | Generated tools, one module per domain |
| `scripts/generate_from_collection.py` | Postman collection → generated modules + `docs/ENDPOINTS.md` |
| `scripts/introspect.py` | GraphQL introspection → `schema/schema.graphql` + `schema.json` |
| `scripts/run.ps1` / `run.sh` / `setup.ps1` / `setup.sh` | Convenience launchers |
| `tests/test_config.py` | Config parsing |
| `tests/test_errors.py` | Error classes |
| `tests/test_client.py` | Client behavior (mocked) |
| `tests/test_common.py` | `execute_operation` helper |
| `tests/test_graphql_tool.py` | Escape-hatch tool + read-only behavior |
| `tests/test_generator.py` | Generator golden test on a fixture collection |
| `tests/test_registration.py` | `register_all` read-only gating + tool counts |
| `tests/fixtures/mini_collection.json` | Tiny 2-domain collection for generator tests |
| `.github/workflows/ci.yml` / `release.yml` | CI (ruff+pytest 3.10–3.12) + publish; CI checks generator is up to date |

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/greymatter_mcp/__init__.py`
- Create: `.env.example`
- Create: `LICENSE`
- Create: `README.md` (skeleton; finalized in Task 13)
- Create: `CHANGELOG.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "greymatter-mcp"
version = "0.1.0"
description = "MCP server for the ReliaQuest GreyMatter GraphQL API"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
license-files = []
authors = [
    { name = "Kierston Grantham", email = "Space-C0wboy@users.noreply.github.com" },
]
keywords = ["mcp", "reliaquest", "greymatter", "security", "soc", "graphql", "ai-tools", "claude"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: System Administrators",
    "Intended Audience :: Information Technology",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Security",
    "Topic :: System :: Systems Administration",
    "Typing :: Typed",
]
dependencies = [
    "fastmcp>=2.0.0,<3.0",
    "httpx>=0.27.0,<1.0",
    "pydantic>=2.6.0,<3.0",
    "python-dotenv>=1.0.0,<2.0",
]

[project.urls]
Homepage = "https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server"
Repository = "https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server"
Issues = "https://github.com/Space-C0wboy/Reliaquest-Greymatter-MCP-Server/issues"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0,<9.0",
    "pytest-asyncio>=0.23.0,<2.0",
    "pytest-httpx>=0.30.0,<1.0",
    "ruff>=0.4.0,<1.0",
]

[project.scripts]
greymatter-mcp = "greymatter_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/greymatter_mcp"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "W"]
ignore = [
    "E501",   # line-too-long — enforced by formatter
    "B008",   # function-call-in-default-argument (FastMCP pattern)
]

[tool.ruff.lint.isort]
known-first-party = ["greymatter_mcp"]

[tool.ruff.lint.per-file-ignores]
"src/greymatter_mcp/tools/_generated/*" = ["E", "W", "B", "UP"]  # machine-generated

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `src/greymatter_mcp/__init__.py`**

```python
"""ReliaQuest GreyMatter MCP server."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.env.example`**

```bash
# Required: your GreyMatter API key (GreyMatter > Settings > API Key Management)
GREYMATTER_API_KEY=

# Optional: GraphQL endpoint (default shown)
GREYMATTER_BASE_URL=https://greymatter.myreliaquest.com/graphql

# Optional: default x-reliaquest-customer header for multi-OpCo accounts ("Header Slug")
GREYMATTER_CUSTOMER_SLUG=

# Optional: when true, no mutation tools are registered and graphql_query is query-only
GREYMATTER_READ_ONLY=false

# Optional: request timeout in seconds (default 30)
GREYMATTER_TIMEOUT=30

# Optional: logging + HTTP transport
LOG_LEVEL=INFO
MCP_HTTP_HOST=127.0.0.1
MCP_HTTP_PORT=8765
```

- [ ] **Step 4: Create `LICENSE` (MIT), `README.md` skeleton, `CHANGELOG.md`**

`LICENSE`: standard MIT text, copyright `2026 Kierston Grantham`.

`README.md` (skeleton — finalized in Task 13):
```markdown
# ReliaQuest GreyMatter MCP Server

MCP server for the ReliaQuest GreyMatter GraphQL API. See `docs/ENDPOINTS.md`.
```

`CHANGELOG.md`:
```markdown
# Changelog

## [Unreleased]
- Initial GreyMatter MCP server.
```

- [ ] **Step 5: Create virtualenv and install**

Run: `python -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"`
Expected: install succeeds; `greymatter-mcp` console script created.

> Note (Windows/PowerShell): use `.venv\Scripts\python` to invoke the venv Python. On bash use `.venv/bin/python`. All later `pytest`/`python` commands assume the venv interpreter.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/greymatter_mcp/__init__.py .env.example LICENSE README.md CHANGELOG.md
git commit -m "chore: project scaffold"
```

---

## Task 2: Config

**Files:**
- Create: `src/greymatter_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from greymatter_mcp.config import Config, ConfigError


def _base_env(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "secret-key")


def test_minimal_config(monkeypatch):
    _base_env(monkeypatch)
    cfg = Config.from_env()
    assert cfg.api_key == "secret-key"
    assert cfg.base_url == "https://greymatter.myreliaquest.com/graphql"
    assert cfg.customer_slug is None
    assert cfg.read_only is False
    assert cfg.timeout == 30.0


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GREYMATTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_read_only_truthy_parsing(monkeypatch):
    _base_env(monkeypatch)
    for val in ("true", "1", "yes", "TRUE"):
        monkeypatch.setenv("GREYMATTER_READ_ONLY", val)
        assert Config.from_env().read_only is True
    for val in ("false", "0", "no", ""):
        monkeypatch.setenv("GREYMATTER_READ_ONLY", val)
        assert Config.from_env().read_only is False


def test_base_url_must_be_http(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GREYMATTER_BASE_URL", "ftp://nope")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_timeout_must_be_number(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GREYMATTER_TIMEOUT", "abc")
    with pytest.raises(ConfigError):
        Config.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError / ImportError for config).

- [ ] **Step 3: Write `src/greymatter_mcp/config.py`**

```python
"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_TRUTHY = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    customer_slug: str | None
    read_only: bool
    timeout: float
    log_level: str
    http_host: str
    http_port: int

    @classmethod
    def from_env(cls) -> Config:
        api_key = os.getenv("GREYMATTER_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "GREYMATTER_API_KEY is required. Set it in your environment or .env file."
            )

        base_url = (
            os.getenv("GREYMATTER_BASE_URL", "https://greymatter.myreliaquest.com/graphql")
            .strip()
            .rstrip("/")
        )
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(
                f"GREYMATTER_BASE_URL must start with http:// or https:// (got {base_url!r})"
            )

        customer_slug = os.getenv("GREYMATTER_CUSTOMER_SLUG", "").strip() or None
        read_only = os.getenv("GREYMATTER_READ_ONLY", "false").strip().lower() in _TRUTHY

        try:
            timeout = float(os.getenv("GREYMATTER_TIMEOUT", "30"))
        except ValueError as e:
            raise ConfigError(f"GREYMATTER_TIMEOUT must be a number: {e}") from e

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        http_host = os.getenv("MCP_HTTP_HOST", "127.0.0.1")
        try:
            http_port = int(os.getenv("MCP_HTTP_PORT", "8765"))
        except ValueError as e:
            raise ConfigError(f"MCP_HTTP_PORT must be an integer: {e}") from e

        return cls(
            api_key=api_key,
            base_url=base_url,
            customer_slug=customer_slug,
            read_only=read_only,
            timeout=timeout,
            log_level=log_level,
            http_host=http_host,
            http_port=http_port,
        )


_config: Config | None = None


def get_config() -> Config:
    """Return the lazily-loaded global config."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config_cache() -> None:
    """Test helper: clear the cached config so the next get_config() re-reads env."""
    global _config
    _config = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Commit**

```bash
git add src/greymatter_mcp/config.py tests/test_config.py
git commit -m "feat: env-based config"
```

---

## Task 3: Errors

**Files:**
- Create: `src/greymatter_mcp/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_errors.py
from greymatter_mcp.errors import GreyMatterAPIError, GreyMatterGraphQLError


def test_api_error_carries_status_and_body():
    err = GreyMatterAPIError(503, "Service Unavailable", body={"x": 1})
    assert err.status_code == 503
    assert err.body == {"x": 1}
    assert "503" in str(err)


def test_graphql_error_summarizes_messages():
    errors = [{"message": "bad enum"}, {"message": "no perms"}]
    err = GreyMatterGraphQLError(errors)
    assert err.errors == errors
    assert "bad enum" in str(err)
    assert "no perms" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_errors.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write `src/greymatter_mcp/errors.py`**

```python
"""Exception types for the GreyMatter client."""

from __future__ import annotations

from typing import Any


class GreyMatterAPIError(RuntimeError):
    """Raised on transport failures or non-2xx HTTP responses."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class GreyMatterGraphQLError(RuntimeError):
    """Raised when a GraphQL response carries a non-empty `errors` array.

    GraphQL returns HTTP 200 even for operation-level errors, so this is
    distinct from the transport-level GreyMatterAPIError.
    """

    def __init__(self, errors: list[dict[str, Any]], data: Any = None):
        messages = "; ".join(str(e.get("message", e)) for e in errors) or "unknown GraphQL error"
        super().__init__(f"GraphQL error: {messages}")
        self.errors = errors
        self.data = data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_errors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/greymatter_mcp/errors.py tests/test_errors.py
git commit -m "feat: error types"
```

---

## Task 4: GraphQL client

**Files:**
- Create: `src/greymatter_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
import pytest

from greymatter_mcp.client import GreyMatterClient
from greymatter_mcp.config import Config
from greymatter_mcp.errors import GreyMatterAPIError, GreyMatterGraphQLError


def _cfg(**over):
    base = dict(
        api_key="k", base_url="https://gm.example/graphql", customer_slug=None,
        read_only=False, timeout=5.0, log_level="INFO", http_host="127.0.0.1", http_port=8765,
    )
    base.update(over)
    return Config(**base)


async def test_execute_returns_data(httpx_mock):
    httpx_mock.add_response(json={"data": {"incidents": {"totalCount": 0}}})
    client = GreyMatterClient(_cfg())
    out = await client.execute("query { incidents { totalCount } }")
    assert out == {"incidents": {"totalCount": 0}}
    req = httpx_mock.get_request()
    assert req.headers["x-api-key"] == "k"
    await client.close()


async def test_graphql_errors_raise(httpx_mock):
    httpx_mock.add_response(json={"errors": [{"message": "bad enum"}], "data": None})
    client = GreyMatterClient(_cfg())
    with pytest.raises(GreyMatterGraphQLError) as ei:
        await client.execute("query { x }")
    assert "bad enum" in str(ei.value)
    await client.close()


async def test_http_error_raises(httpx_mock):
    httpx_mock.add_response(status_code=401, json={"message": "unauthorized"})
    client = GreyMatterClient(_cfg())
    with pytest.raises(GreyMatterAPIError) as ei:
        await client.execute("query { x }")
    assert ei.value.status_code == 401
    await client.close()


async def test_customer_slug_header_per_call(httpx_mock):
    httpx_mock.add_response(json={"data": {"ok": True}})
    client = GreyMatterClient(_cfg())
    await client.execute("query { ok }", customer_slug="opco-7")
    assert httpx_mock.get_request().headers["x-reliaquest-customer"] == "opco-7"
    await client.close()


async def test_default_customer_slug_from_config(httpx_mock):
    httpx_mock.add_response(json={"data": {"ok": True}})
    client = GreyMatterClient(_cfg(customer_slug="default-opco"))
    await client.execute("query { ok }")
    assert httpx_mock.get_request().headers["x-reliaquest-customer"] == "default-opco"
    await client.close()


async def test_retries_on_503_then_succeeds(httpx_mock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(json={"data": {"ok": True}})
    client = GreyMatterClient(_cfg())
    out = await client.execute("query { ok }")
    assert out == {"ok": True}
    assert len(httpx_mock.get_requests()) == 2
    await client.close()
```

> Note: `pytest-httpx` provides the `httpx_mock` fixture. `asyncio_mode = auto` lets `async def test_*` run without decorators.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_client.py -v`
Expected: FAIL (ImportError for client).

- [ ] **Step 3: Write `src/greymatter_mcp/client.py`**

```python
"""Async GraphQL client for the ReliaQuest GreyMatter API."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import Config, get_config
from .errors import GreyMatterAPIError, GreyMatterGraphQLError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_MAX_RETRY_AFTER_SECONDS = 60.0


def _parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None
    value = header_value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class GreyMatterClient:
    """Thin async wrapper over the single GreyMatter GraphQL endpoint.

    Auth: every request sends `X-API-KEY`. Multi-OpCo accounts may set the
    `x-reliaquest-customer` header (default from config, overridable per call).
    """

    def __init__(self, config: Config | None = None):
        self._config = config or get_config()
        self._client: httpx.AsyncClient | None = None
        self._connect_lock = asyncio.Lock()

    async def __aenter__(self) -> GreyMatterClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url="",
                    timeout=self._config.timeout,
                    headers={
                        "X-API-KEY": self._config.api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "greymatter-mcp/0.1.0",
                    },
                )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self, customer_slug: str | None) -> dict[str, str]:
        slug = customer_slug or self._config.customer_slug
        return {"x-reliaquest-customer": slug} if slug else {}

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        customer_slug: str | None = None,
    ) -> Any:
        """Run a GraphQL document and return its `data` object.

        Raises GreyMatterGraphQLError if the response carries an `errors` array,
        GreyMatterAPIError on transport/HTTP failures. Retries transient errors
        (429/5xx/network) with exponential backoff + jitter, honoring Retry-After.
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None

        payload = {"query": query, "variables": variables or {}}
        headers = self._headers(customer_slug)

        next_backoff: float | None = None
        for attempt in range(_MAX_RETRIES):
            if next_backoff is not None:
                logger.warning("Retry %d/%d — backing off %.2fs", attempt, _MAX_RETRIES - 1, next_backoff)
                await asyncio.sleep(next_backoff)
                next_backoff = None

            try:
                response = await self._client.post(
                    self._config.base_url, json=payload, headers=headers
                )
            except httpx.HTTPError as e:
                if attempt == _MAX_RETRIES - 1:
                    raise GreyMatterAPIError(0, f"Network error: {e}") from e
                logger.warning("Network error on attempt %d: %s", attempt + 1, e)
                next_backoff = random.uniform(0, 2**attempt)
                continue

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                next_backoff = (
                    min(retry_after, _MAX_RETRY_AFTER_SECONDS)
                    if retry_after is not None
                    else random.uniform(0, 2**attempt)
                )
                logger.warning("HTTP %d — will retry", response.status_code)
                continue

            if response.status_code >= 400:
                try:
                    body: Any = response.json()
                except ValueError:
                    body = response.text
                message = (
                    body.get("message") or body.get("error") or str(body)
                    if isinstance(body, dict)
                    else str(body)
                )
                raise GreyMatterAPIError(response.status_code, message, body)

            try:
                parsed = response.json()
            except ValueError as e:
                raise GreyMatterAPIError(
                    response.status_code, f"Non-JSON response: {e}", response.text
                ) from e

            errors = parsed.get("errors") if isinstance(parsed, dict) else None
            if errors:
                raise GreyMatterGraphQLError(errors, data=parsed.get("data"))
            return parsed.get("data") if isinstance(parsed, dict) else parsed

        raise GreyMatterAPIError(0, "Max retries exceeded")  # pragma: no cover


_client: GreyMatterClient | None = None
_client_lock = asyncio.Lock()


async def get_client() -> GreyMatterClient:
    """Return a process-wide shared client (one connection pool)."""
    global _client
    async with _client_lock:
        if _client is None:
            _client = GreyMatterClient()
            await _client.connect()
    return _client


async def shutdown_client() -> None:
    global _client
    async with _client_lock:
        if _client is not None:
            await _client.close()
            _client = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: PASS (6 tests). The retry test exercises the 503→200 path.

- [ ] **Step 5: Commit**

```bash
git add src/greymatter_mcp/client.py tests/test_client.py
git commit -m "feat: async GraphQL client with retry and GraphQL-error handling"
```

---

## Task 5: Shared tool helper (`_common`)

**Files:**
- Create: `src/greymatter_mcp/tools/__init__.py` (temporary minimal; filled in Task 9)
- Create: `src/greymatter_mcp/tools/_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Create empty package marker**

Create `src/greymatter_mcp/tools/__init__.py` with a single line (replaced in Task 9):
```python
"""GreyMatter MCP tools."""
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_common.py
from greymatter_mcp.tools._common import drop_none, execute_operation


def test_drop_none_filters_only_none():
    assert drop_none({"a": 1, "b": None, "c": False, "d": ""}) == {"a": 1, "c": False, "d": ""}


async def test_execute_operation_uses_shared_client(monkeypatch):
    calls = {}

    class FakeClient:
        async def execute(self, query, variables=None, *, customer_slug=None):
            calls["query"] = query
            calls["variables"] = variables
            calls["customer_slug"] = customer_slug
            return {"ok": True}

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr("greymatter_mcp.tools._common.get_client", fake_get_client)
    out = await execute_operation("query { ok }", {"a": 1, "b": None}, customer_slug="opco")
    assert out == {"ok": True}
    assert calls["variables"] == {"a": 1}  # None dropped
    assert calls["customer_slug"] == "opco"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_common.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 4: Write `src/greymatter_mcp/tools/_common.py`**

```python
"""Shared helpers for generated GreyMatter tools."""

from __future__ import annotations

from typing import Any

from ..client import get_client


def drop_none(variables: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is None so optional GraphQL variables are omitted."""
    return {k: v for k, v in variables.items() if v is not None}


async def execute_operation(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    customer_slug: str | None = None,
) -> Any:
    """Run a GraphQL document via the shared client, omitting None variables."""
    client = await get_client()
    return await client.execute(
        query, drop_none(variables or {}), customer_slug=customer_slug
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_common.py -v`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add src/greymatter_mcp/tools/__init__.py src/greymatter_mcp/tools/_common.py tests/test_common.py
git commit -m "feat: shared tool execution helper"
```

---

## Task 6: Escape-hatch tool (`graphql_query`)

**Files:**
- Create: `src/greymatter_mcp/tools/graphql.py`
- Test: `tests/test_graphql_tool.py`

The escape hatch runs arbitrary documents. When `read_only` is true it must reject mutations (detected by the leading operation keyword).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graphql_tool.py
import pytest

from greymatter_mcp.tools.graphql import is_mutation_document


def test_detects_mutation():
    assert is_mutation_document("mutation Foo { x }") is True
    assert is_mutation_document("  \n  mutation { x }") is True


def test_detects_query():
    assert is_mutation_document("query Foo { x }") is False
    assert is_mutation_document("{ x }") is False  # shorthand query


def test_ignores_leading_comments():
    assert is_mutation_document("# a comment\nmutation { x }") is True
    assert is_mutation_document("# comment\nquery { x }") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graphql_tool.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write `src/greymatter_mcp/tools/graphql.py`**

```python
"""Generic GraphQL escape-hatch tool."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from ._common import execute_operation

# Strip leading whitespace and full-line comments, then read the first keyword.
_LEADING = re.compile(r"^\s*(?:#[^\n]*\n\s*)*")


def is_mutation_document(query: str) -> bool:
    """True if the document's first operation is a mutation."""
    stripped = _LEADING.sub("", query)
    return stripped.lstrip().lower().startswith("mutation")


def register(mcp: FastMCP, *, read_only: bool) -> None:
    @mcp.tool(
        name="graphql_query",
        description=(
            "Run an arbitrary GraphQL document against the GreyMatter API. Use this "
            "for operations not covered by a dedicated tool. Provide the full query/"
            "mutation string and an optional variables object. When the server is in "
            "read-only mode, mutation documents are rejected."
        ),
    )
    async def graphql_query(
        query: Annotated[str, Field(description="The full GraphQL query or mutation document.")],
        variables: Annotated[
            dict | None,
            Field(default=None, description="Variables object for the document."),
        ] = None,
        customer_slug: Annotated[
            str | None,
            Field(default=None, description="Override the x-reliaquest-customer (OpCo) header."),
        ] = None,
    ) -> Any:
        if read_only and is_mutation_document(query):
            raise ValueError(
                "Server is in read-only mode (GREYMATTER_READ_ONLY); mutations are disabled."
            )
        return await execute_operation(query, variables, customer_slug=customer_slug)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graphql_tool.py -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add src/greymatter_mcp/tools/graphql.py tests/test_graphql_tool.py
git commit -m "feat: graphql_query escape-hatch tool"
```

---

## Task 7: Collection generator

**Files:**
- Create: `scripts/generate_from_collection.py`
- Create: `tests/fixtures/mini_collection.json`
- Test: `tests/test_generator.py`

The generator parses the Postman collection and emits, per domain folder, a module of FastMCP tools. It also emits `_generated/__init__.py` (with `GENERATED_MODULES`) and `docs/ENDPOINTS.md`.

**Emitted tool shape (the generator produces this source per operation):**

```python
def register(mcp, *, read_only):
    # --- queries (always registered) ---
    @mcp.tool(name="incidents", description="...")
    async def incidents(
        after: Annotated[str | None, Field(default=None, description="GraphQL: String")] = None,
        first: Annotated[int | None, Field(default=None, description="GraphQL: Int")] = None,
        incidentFilter: Annotated[Any | None, Field(default=None, description="GraphQL: IncidentFilter (object)")] = None,
        incidentOrder: Annotated[Any | None, Field(default=None, description="GraphQL: IncidentOrder (object)")] = None,
        customer_slug: Annotated[str | None, Field(default=None, description="Override x-reliaquest-customer (OpCo) header.")] = None,
    ) -> Any:
        return await execute_operation(_DOC["incidents"], {"after": after, "first": first, "incidentFilter": incidentFilter, "incidentOrder": incidentOrder}, customer_slug=customer_slug)

    if not read_only:
        @mcp.tool(name="acknowledge_incident", description="...")
        async def acknowledge_incident(
            input: Annotated[Any, Field(description="GraphQL: IncidentAcknowledgementInput! (object). Example: {...}")],
            customer_slug: Annotated[str | None, Field(default=None, description="Override x-reliaquest-customer (OpCo) header.")] = None,
        ) -> Any:
            return await execute_operation(_DOC["acknowledgeIncident"], {"input": input}, customer_slug=customer_slug)
```

- [ ] **Step 1: Create the fixture `tests/fixtures/mini_collection.json`**

```json
{
  "info": { "name": "Mini GreyMatter" },
  "item": [
    {
      "name": "Incidents",
      "item": [
        {
          "name": "Queries",
          "item": [
            {
              "name": "incidents",
              "request": {
                "method": "POST",
                "body": {
                  "mode": "graphql",
                  "graphql": {
                    "query": "query incidents ($after: String, $first: Int, $incidentFilter: IncidentFilter) {\n incidents (after: $after, first: $first, incidentFilter: $incidentFilter) {\n totalCount\n }\n}",
                    "variables": "{\n \"first\": 10\n}"
                  }
                }
              }
            }
          ]
        },
        {
          "name": "Mutations",
          "item": [
            {
              "name": "acknowledgeIncident",
              "request": {
                "method": "POST",
                "body": {
                  "mode": "graphql",
                  "graphql": {
                    "query": "mutation acknowledgeIncident ($input: IncidentAcknowledgementInput!) {\n acknowledgeIncident (input: $input) {\n success\n }\n}",
                    "variables": "{\n \"input\": {\n \"incidentId\": \"x\"\n }\n}"
                  }
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_generator.py
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path("scripts/generate_from_collection.py")


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_variable_decls_simple():
    gen = _load_generator()
    sig = "($after: String, $first: Int, $incidentFilter: IncidentFilter)"
    decls = gen.parse_variable_decls(sig)
    assert decls == [
        ("after", "String", False),
        ("first", "Int", False),
        ("incidentFilter", "IncidentFilter", False),
    ]


def test_parse_variable_decls_required_and_list():
    gen = _load_generator()
    decls = gen.parse_variable_decls("($input: IncidentAcknowledgementInput!, $ids: [ID!]!)")
    assert decls == [
        ("input", "IncidentAcknowledgementInput!", True),
        ("ids", "[ID!]!", True),
    ]


def test_python_annotation_mapping():
    gen = _load_generator()
    assert gen.py_annotation("String") == "str | None"
    assert gen.py_annotation("Int") == "int | None"
    assert gen.py_annotation("Boolean") == "bool | None"
    assert gen.py_annotation("ID!") == "str"
    assert gen.py_annotation("IncidentFilter") == "Any | None"
    assert gen.py_annotation("[ID!]!") == "list"


def test_tool_name_snake_case():
    gen = _load_generator()
    assert gen.tool_name("acknowledgeIncident") == "acknowledge_incident"
    assert gen.tool_name("incidents") == "incidents"
    assert gen.tool_name("runPlaybook") == "run_playbook"
    assert gen.tool_name("upsertCustomerPlaybook") == "upsert_customer_playbook"


def test_generate_writes_modules(tmp_path):
    gen = _load_generator()
    out_dir = tmp_path / "_generated"
    docs = tmp_path / "ENDPOINTS.md"
    gen.generate(
        collection_path=Path("tests/fixtures/mini_collection.json"),
        out_dir=out_dir,
        endpoints_doc=docs,
    )
    incidents = (out_dir / "incidents.py").read_text()
    assert "def register(mcp" in incidents
    assert 'name="incidents"' in incidents
    assert 'name="acknowledge_incident"' in incidents
    assert "if not read_only:" in incidents  # mutation gated
    init = (out_dir / "__init__.py").read_text()
    assert "GENERATED_MODULES" in init
    assert "incidents" in init
    assert docs.read_text().count("acknowledge_incident") >= 1


def test_generated_module_imports_and_registers(tmp_path):
    """The emitted code must be valid Python and register tools on a FastMCP."""
    gen = _load_generator()
    out_dir = tmp_path / "_generated"
    gen.generate(
        collection_path=Path("tests/fixtures/mini_collection.json"),
        out_dir=out_dir,
        endpoints_doc=tmp_path / "ENDPOINTS.md",
    )
    # Compile each generated module to ensure it's syntactically valid.
    for py in out_dir.glob("*.py"):
        compile(py.read_text(), str(py), "exec")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_generator.py -v`
Expected: FAIL (script not found / attrs missing).

- [ ] **Step 4: Write `scripts/generate_from_collection.py`**

```python
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
from typing import Any

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

_OP_RE = re.compile(r"^\s*(query|mutation)\s+([A-Za-z0-9_]+)?\s*(\([^)]*\))?", re.DOTALL)


def parse_operation(query: str) -> tuple[str, str, str]:
    """Return (kind, operation_name, signature) for a GraphQL document.

    signature is the raw "(...)" variable-declaration block, or "" if none.
    """
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
    # Split on top-level commas (variable types here have no nested commas).
    for part in inner.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name_part, type_part = part.split(":", 1)
        name = name_part.strip().lstrip("$")
        gql_type = type_part.strip()
        required = gql_type.endswith("!") and not gql_type.startswith("[")
        # A bare "Foo!" is required; "[X]" / "[X!]" treated as list (see py_annotation).
        if gql_type.endswith("!") and not gql_type.startswith("["):
            required = True
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
    # Enums, input objects, custom scalars (DateTime, Long, ...) -> Any/dict-ish.
    return "Any" if required else "Any | None"


def tool_name(op_name: str) -> str:
    """camelCase / PascalCase GraphQL field -> snake_case tool name."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", op_name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def module_name(folder: str) -> str:
    """Domain folder name -> snake_case module filename (no extension)."""
    s = folder.strip().replace("-", " ").replace("/", " ")
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"[^a-z0-9_]", "", s.lower())


def _iter_requests(items: list[dict], top_folder: str | None = None):
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
    """Group operations by module name. Each op: {kind, op_name, sig, query, example}."""
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
    # Deterministic ordering: module name, then queries before mutations, then op name.
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
    """Compact one-line example for a tool description; '' if unusable."""
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
    desc = f"{op['folder']} · {op['kind']} {op['op_name']}."
    if decls:
        desc += " Variables: " + ", ".join(d[0] for d in decls) + "."
    if example:
        desc = desc + f" Example variables: {example}"
    desc = desc.replace('"', '\\"')

    params: list[str] = []
    var_items: list[str] = []
    # Required params first (no default), then optional, then customer_slug.
    ordered = sorted(decls, key=lambda d: not d[2])
    for var_name, gql_type, required in ordered:
        annot = py_annotation(gql_type)
        pdesc = f"GraphQL: {gql_type}"
        pdesc = pdesc.replace('"', '\\"')
        if required:
            params.append(
                f'        {var_name}: Annotated[{annot}, Field(description="{pdesc}")],'
            )
        else:
            params.append(
                f'        {var_name}: Annotated[{annot}, Field(default=None, description="{pdesc}")] = None,'
            )
        var_items.append(f'"{var_name}": {var_name}')
    params.append(
        '        customer_slug: Annotated[str | None, Field(default=None, '
        'description="Override the x-reliaquest-customer (OpCo) header.")] = None,'
    )
    var_dict = "{" + ", ".join(var_items) + "}"
    indent = "    " if op["kind"] == "mutation" else ""

    lines = []
    if op["kind"] == "mutation":
        # Caller wraps mutations in `if not read_only:` (added in _emit_module).
        pass
    body = f'''{indent}    @mcp.tool(name="{name}", description="{desc}")
{indent}    async def {name}(
{chr(10).join((indent + p) for p in params)}
{indent}    ) -> Any:
{indent}        return await execute_operation(_DOC["{op['op_name']}"], {var_dict}, customer_slug=customer_slug)
'''
    return body


def _emit_module(folder: str, ops: list[dict]) -> str:
    docs = {op["op_name"]: op["query"] for op in ops}
    alldocs = "{\n" + "\n".join(
        f"    {json.dumps(k)}: {json.dumps(v)}," for k, v in docs.items()
    ) + "\n}"
    out = _HEADER.replace("{folder}", folder).replace("{ALLDOCS}", alldocs)

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

    out_dir.mkdir(parents=True, exist_ok=True)
    # Clean stale generated modules.
    for old in out_dir.glob("*.py"):
        old.unlink()

    folder_for_module: dict[str, str] = {}
    for mod, ops in by_module.items():
        folder_for_module[mod] = ops[0]["folder"]
        (out_dir / f"{mod}.py").write_text(_emit_module(ops[0]["folder"], ops), encoding="utf-8")

    # _generated/__init__.py with the registry.
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

    # docs/ENDPOINTS.md catalog.
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_generator.py -v`
Expected: PASS (6). If the emitted-code compile test fails, fix `_emit_tool`/`_emit_module` indentation until `compile()` succeeds.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_from_collection.py tests/fixtures/mini_collection.json tests/test_generator.py
git commit -m "feat: Postman-collection tool generator"
```

---

## Task 8: Generate the real tool modules

**Files:**
- Create (generated): `src/greymatter_mcp/tools/_generated/*.py`, `docs/ENDPOINTS.md`

- [ ] **Step 1: Run the generator against the real collection**

Run: `.venv\Scripts\python scripts/generate_from_collection.py`
Expected: prints `Generated <N> tools across <M> modules ...` with N ≈ 150, M ≈ 22.

- [ ] **Step 2: Verify all generated modules compile and import**

Run:
```bash
.venv\Scripts\python -c "import compileall, sys; sys.exit(0 if compileall.compile_dir('src/greymatter_mcp/tools/_generated', quiet=1) else 1)"
```
Expected: exit 0 (all generated modules are valid Python).

- [ ] **Step 3: Sanity-check the catalog**

Run: open `docs/ENDPOINTS.md`; confirm domains (Incidents, Tasks, Detections, Playbooks, Cases, DRP Alerts, etc.) and a plausible total (~150).

- [ ] **Step 4: Commit the generated output**

```bash
git add src/greymatter_mcp/tools/_generated docs/ENDPOINTS.md
git commit -m "feat: generate GreyMatter tool modules from collection"
```

---

## Task 9: Registration with read-only gating

**Files:**
- Modify: `src/greymatter_mcp/tools/__init__.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registration.py
import pytest
from fastmcp import FastMCP

from greymatter_mcp import config
from greymatter_mcp.tools import register_all


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "k")
    config.reset_config_cache()
    yield
    config.reset_config_cache()


async def _tool_names(mcp) -> set[str]:
    tools = await mcp.get_tools()
    return set(tools.keys())


async def test_read_write_registers_mutations(monkeypatch):
    monkeypatch.setenv("GREYMATTER_READ_ONLY", "false")
    config.reset_config_cache()
    mcp = FastMCP(name="t")
    register_all(mcp)
    names = await _tool_names(mcp)
    assert "incidents" in names
    assert "acknowledge_incident" in names  # a mutation
    assert "graphql_query" in names


async def test_read_only_hides_mutations(monkeypatch):
    monkeypatch.setenv("GREYMATTER_READ_ONLY", "true")
    config.reset_config_cache()
    mcp = FastMCP(name="t")
    register_all(mcp)
    names = await _tool_names(mcp)
    assert "incidents" in names           # query still present
    assert "acknowledge_incident" not in names  # mutation hidden
    assert "graphql_query" in names       # escape hatch present (query-only)
```

> Note: confirm the FastMCP introspection call for registered tools. If `get_tools()` differs in the installed FastMCP version, use the documented equivalent (e.g. `mcp._tool_manager` listing) — adjust the helper, keep the assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_registration.py -v`
Expected: FAIL (`register_all` not defined).

- [ ] **Step 3: Write `src/greymatter_mcp/tools/__init__.py`**

```python
"""GreyMatter MCP tool registry."""

from __future__ import annotations

from fastmcp import FastMCP

from ..config import get_config
from . import graphql
from ._generated import GENERATED_MODULES


def register_all(mcp: FastMCP) -> None:
    """Register every tool. Mutation tools are skipped when read-only is set."""
    read_only = get_config().read_only
    for module in GENERATED_MODULES:
        module.register(mcp, read_only=read_only)
    graphql.register(mcp, read_only=read_only)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_registration.py -v`
Expected: PASS (2).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/greymatter_mcp/tools/__init__.py tests/test_registration.py
git commit -m "feat: tool registration with read-only gating"
```

---

## Task 10: Server entrypoint

**Files:**
- Create: `src/greymatter_mcp/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
from fastmcp import FastMCP

from greymatter_mcp import config
from greymatter_mcp.server import build_server


def test_build_server(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "k")
    config.reset_config_cache()
    mcp = build_server()
    assert isinstance(mcp, FastMCP)
    config.reset_config_cache()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write `src/greymatter_mcp/server.py`**

```python
"""GreyMatter MCP server — entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys

from fastmcp import FastMCP

from .client import shutdown_client
from .config import ConfigError, get_config
from .tools import register_all


def build_server() -> FastMCP:
    config = get_config()  # validates env early

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdio transport owns stdout
    )

    mcp = FastMCP(
        name="greymatter-mcp",
        instructions=(
            "MCP server for the ReliaQuest GreyMatter GraphQL API. Tools are grouped "
            "by domain (incidents, tasks, detections, playbooks, cases, DRP alerts, "
            "etc.). Use `graphql_query` for anything without a dedicated tool. For "
            "multi-OpCo accounts, pass `customer_slug` to target a company. Check "
            "remaining API budget with the `rate_limit` tool. When the server runs "
            "with GREYMATTER_READ_ONLY=true, mutation tools are hidden and "
            "`graphql_query` rejects mutations."
        ),
    )
    register_all(mcp)
    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(prog="greymatter-mcp")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    try:
        mcp = build_server()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    config = get_config()
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(
                transport="http",
                host=args.host or config.http_host,
                port=args.port or config.http_port,
            )
    finally:
        import asyncio

        try:
            asyncio.run(shutdown_client())
        except RuntimeError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke-test the stdio server boots**

Run (PowerShell): `$env:GREYMATTER_API_KEY="k"; .venv\Scripts\python -c "from greymatter_mcp.server import build_server; build_server(); print('ok')"`
Expected: prints `ok` (no exceptions).

- [ ] **Step 6: Commit**

```bash
git add src/greymatter_mcp/server.py tests/test_server.py
git commit -m "feat: FastMCP server entrypoint"
```

---

## Task 11: Introspection script

**Files:**
- Create: `scripts/introspect.py`

This is an operator utility (verification), not unit-tested (it hits the live API). Keep it small and dependency-light.

- [ ] **Step 1: Write `scripts/introspect.py`**

```python
"""Fetch the live GreyMatter GraphQL schema via introspection.

Usage:
    python scripts/introspect.py

Reads GREYMATTER_API_KEY (and optional GREYMATTER_BASE_URL,
GREYMATTER_CUSTOMER_SLUG) from the environment / .env. Writes
schema/schema.json (raw introspection) and schema/schema.graphql (SDL).
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
```

- [ ] **Step 2: Lint it**

Run: `.venv\Scripts\ruff check scripts/introspect.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/introspect.py
git commit -m "feat: GraphQL introspection script"
```

> Operator step (manual, not part of automated tests): with a real key in `.env`, run `.venv\Scripts\python scripts/introspect.py` and commit `schema/schema.graphql` for reference. Use it to confirm enum/input-type names in high-traffic tools.

---

## Task 12: Convenience scripts + CI

**Files:**
- Create: `scripts/run.ps1`, `scripts/run.sh`, `scripts/setup.ps1`, `scripts/setup.sh`
- Create: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: Create launcher scripts**

`scripts/setup.ps1`:
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```
`scripts/setup.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```
`scripts/run.ps1`:
```powershell
.\.venv\Scripts\python -m greymatter_mcp.server @args
```
`scripts/run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
./.venv/bin/python -m greymatter_mcp.server "$@"
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
```

- [ ] **Step 3: Create `.github/workflows/release.yml`**

```yaml
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/*
```

- [ ] **Step 4: Verify lint + tests pass locally**

Run: `.venv\Scripts\ruff check .; .venv\Scripts\pytest -q`
Expected: ruff clean (generated modules are ignored per pyproject), tests green.

- [ ] **Step 5: Commit**

```bash
git add scripts/run.ps1 scripts/run.sh scripts/setup.ps1 scripts/setup.sh .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "chore: launcher scripts and CI"
```

---

## Task 13: README + high-traffic tool polish

**Files:**
- Modify: `README.md`
- Modify (optional): selected `src/greymatter_mcp/tools/_generated/*.py` descriptions via a name/description override map in the generator

- [ ] **Step 1: Write the full `README.md`**

Include: overview; install (`pip install -e .` / uv); `.env` setup (all vars from §6.1); Claude Desktop config snippet (stdio, command `greymatter-mcp`); read-only mode explanation; multi-OpCo `customer_slug` note; how tools are generated (`scripts/generate_from_collection.py`) and that `Development Reference/` is required locally but gitignored; link to `docs/ENDPOINTS.md`; rate-limit note (5000 pts/hr, `rate_limit` tool); support contact (greymattersupport@reliaquest.com). Mirror the structure of the ThreatLocker README.

Claude Desktop snippet to include:
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

- [ ] **Step 2: (Optional) polish high-traffic SOC tool descriptions**

If desired, add an `OVERRIDES` dict to the generator keyed by `op_name` that supplies a richer description for the most-used SOC operations (`incidents`, `incident`, `acknowledge_incident`, `assign_incident`, `add_incident_comment`, `close_incident`, `update_incident_state`, `tasks`, `task`, `resolve_task`, `detection_rules`, `run_playbook`), e.g. close-code enum guidance for `close_incident`. Re-run the generator and re-commit `_generated/` + `docs/ENDPOINTS.md`. Keep overrides in the generator so regeneration preserves them.

- [ ] **Step 3: Update CHANGELOG**

Move items under a `## [0.1.0]` heading with today's date.

- [ ] **Step 4: Final full-suite run**

Run: `.venv\Scripts\ruff check .; .venv\Scripts\pytest -q`
Expected: clean + green.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md scripts/generate_from_collection.py src/greymatter_mcp/tools/_generated docs/ENDPOINTS.md
git commit -m "docs: README, changelog, tool description polish"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** config (§6.1) → Task 2; client + GraphQL-error-on-200 + retry (§6.2) → Task 4; errors (§6.3) → Task 3; generation (§4, §6.5) → Tasks 7–8; registration + read-only (§6.4) → Task 9; escape hatch (§7) → Task 6; server (§9) → Task 10; introspection (§8) → Task 11; tests (§11) → throughout; CI (§12) → Task 12; ENDPOINTS.md (§5) → Task 8; README → Task 13. `Development Reference/` gitignore (§2) already done.
- **FastMCP API drift:** the only version-sensitive spot is the tool-listing call in Task 9's test helper (`get_tools()`). If the installed FastMCP exposes tools differently, adjust the helper only; assertions stand.
- **Generated-code validity:** Task 7's `test_generated_module_imports_and_registers` compiles every emitted module; Task 8 step 2 compiles the real output. If indentation in `_emit_tool` is wrong, these fail fast.
- **Determinism:** `_collect` sorts modules and operations; re-running the generator yields identical files (CI can diff).
