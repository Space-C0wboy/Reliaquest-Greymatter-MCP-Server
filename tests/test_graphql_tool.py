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
