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
