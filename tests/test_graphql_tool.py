import pytest
from fastmcp import FastMCP

from greymatter_mcp.tools import graphql as gql_tool
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


def test_fragment_prefixed_mutation_is_detected():
    doc = "fragment F on Thing { a }\nmutation Do { x }"
    assert is_mutation_document(doc) is True


def test_fragment_prefixed_query_is_not_mutation():
    doc = "fragment F on Thing { a }\nquery Get { x }"
    assert is_mutation_document(doc) is False


def test_bom_prefixed_mutation_is_detected():
    assert is_mutation_document("﻿mutation { x }") is True


def test_multiple_fragments_then_mutation():
    doc = "fragment A on T { a }\nfragment B on T { b }\nmutation M { go }"
    assert is_mutation_document(doc) is True


def test_trailing_mutation_in_multi_operation_document_is_detected():
    assert is_mutation_document("query a { x } mutation b { y }")


def test_multiple_query_operations_are_not_a_mutation():
    assert not is_mutation_document("query a { x } query b { y }")


def test_fragment_then_query_then_mutation_is_detected():
    assert is_mutation_document(
        "fragment f on T { x } query a { ...f } mutation b { y }"
    )


# --- string-literal handling (Codex review: braces/keywords inside string values) ---

def test_brace_inside_string_does_not_misclassify_query():
    # The closing brace and the word "mutation" live inside a string value; this is
    # a read-only query and must NOT be flagged as a mutation.
    assert is_mutation_document('query { search(q: "} mutation") { id } }') is False


def test_mutation_keyword_inside_string_is_not_a_mutation():
    assert is_mutation_document('query { search(q: "mutation") { id } }') is False


def test_block_string_with_braces_and_keyword_is_not_a_mutation():
    assert is_mutation_document('query { f(note: """ } mutation { """) { id } }') is False


def test_real_mutation_with_string_containing_brace_still_detected():
    assert is_mutation_document('mutation { addComment(text: "}") { id } }') is True


def test_string_default_value_with_brace_is_not_a_mutation():
    assert is_mutation_document('query x($a: String = "}") { f(a: $a) { id } }') is False


async def _get_tool_fn(read_only: bool):
    mcp = FastMCP(name="t")
    gql_tool.register(mcp, read_only=read_only)
    tools = await mcp.get_tools()
    tool = tools["graphql_query"]
    return getattr(tool, "fn", None) or getattr(tool, "_fn", None) or tool


async def test_graphql_query_blocks_mutation_when_read_only(monkeypatch):
    async def fake_exec(query, variables=None, *, customer_slug=None):
        return {"should_not": "run"}
    monkeypatch.setattr("greymatter_mcp.tools.graphql.execute_operation", fake_exec)
    fn = await _get_tool_fn(read_only=True)
    with pytest.raises(ValueError):
        await fn(query="mutation { acknowledgeIncident(input: {}) { success } }")


async def test_graphql_query_allows_query_when_read_only(monkeypatch):
    async def fake_exec(query, variables=None, *, customer_slug=None):
        return {"ok": True}
    monkeypatch.setattr("greymatter_mcp.tools.graphql.execute_operation", fake_exec)
    fn = await _get_tool_fn(read_only=True)
    out = await fn(query="query { incidents { totalCount } }")
    assert out == {"ok": True}


async def test_read_only_allows_query_with_brace_in_string(monkeypatch):
    # A read query whose string value contains "}" and "mutation" must not be
    # blocked by read-only mode (Codex review regression).
    async def fake_exec(query, variables=None, *, customer_slug=None):
        return {"ok": True}
    monkeypatch.setattr("greymatter_mcp.tools.graphql.execute_operation", fake_exec)
    fn = await _get_tool_fn(read_only=True)
    out = await fn(query='query { search(q: "} mutation") { id } }')
    assert out == {"ok": True}
