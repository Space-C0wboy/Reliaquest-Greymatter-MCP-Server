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


def test_no_order_parameter_described_as_a_filter_type():
    # The generator also derives each tool parameter's "GraphQL: <Type>"
    # description from the document's variable declarations. An order parameter
    # described as a *Filter type is the same typo surfacing in the tool's
    # signature; guard it too since the mechanical fix touches descriptions
    # separately from the _DOC strings.
    import inspect

    pattern = re.compile(r'order\d*: Annotated\[[^\]]*description="GraphQL: \w*Filter"')
    for module in GENERATED_MODULES:
        source = inspect.getsource(module)
        match = pattern.search(source)
        assert match is None, f"{module.__name__}: {match.group(0)}"


def _nested_roles_args(document):
    # (args, brace depth) for every roles(...) selection; depth 1 is the operation's root field.
    for m in re.finditer(r"(?<![A-Za-z0-9_$])roles\s*\(([^)]*)\)", document):
        depth = document[: m.start()].count("{") - document[: m.start()].count("}")
        yield m.group(1), depth


def test_nested_roles_selections_carry_no_order_argument():
    # Issue #32: the live schema types User.roles(order:) as RoleFilter, so any $orderN
    # passed there fails validation. Nested roles selections must not pass order at all.
    for module in GENERATED_MODULES:
        for op_name, document in module._DOC.items():
            for args, depth in _nested_roles_args(document):
                if depth >= 2:
                    assert "order:" not in args, f"{module.__name__}.{op_name}: roles({args})"


def test_every_declared_variable_is_used_and_passed():
    # The documents were edited in place (no collection on hand to regenerate), so pin the
    # invariant regeneration guarantees: each tool forwards exactly its document's variables.
    import inspect

    for module in GENERATED_MODULES:
        source = inspect.getsource(module)
        for op_name, document in module._DOC.items():
            sig, _, body = document.partition("{")
            declared = re.findall(r"\$(\w+)\s*:", sig)
            for name in declared:
                assert re.search(rf"\${name}(?!\w)", body), (
                    f"{module.__name__}.{op_name}: ${name} unused"
                )
            call = re.search(
                rf'execute_operation\(_DOC\["{op_name}"\], \{{(.*?)\}}, customer_slug', source
            )
            assert call, f"{module.__name__}.{op_name}: no execute_operation call"
            passed = re.findall(r'"(\w+)":', call.group(1))
            assert sorted(passed) == sorted(declared), (
                f"{module.__name__}.{op_name}: passes {passed}, declares {declared}"
            )
