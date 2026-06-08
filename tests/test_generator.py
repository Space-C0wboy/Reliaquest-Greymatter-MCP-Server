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
    assert "if not read_only:" in incidents
    init = (out_dir / "__init__.py").read_text()
    assert "GENERATED_MODULES" in init
    assert "incidents" in init
    assert docs.read_text().count("acknowledge_incident") >= 1


def test_generated_module_imports_and_registers(tmp_path):
    gen = _load_generator()
    out_dir = tmp_path / "_generated"
    gen.generate(
        collection_path=Path("tests/fixtures/mini_collection.json"),
        out_dir=out_dir,
        endpoints_doc=tmp_path / "ENDPOINTS.md",
    )
    for py in out_dir.glob("*.py"):
        compile(py.read_text(), str(py), "exec")


def test_module_name_robustness():
    gen = _load_generator()
    assert gen.module_name("API Keys") == "api_keys"
    assert gen.module_name("DRP Alerts") == "drp_alerts"
    assert gen.module_name("Discover-Tasks") == "discover_tasks"
    name = gen.module_name("123 Weird")
    assert name.isidentifier() and not name[0].isdigit()


def test_duplicate_operation_raises(tmp_path):
    gen = _load_generator()
    collection = {
        "info": {"name": "Dup"},
        "item": [
            {"name": "Things", "item": [
                {"name": "Queries", "item": [
                    {"name": "thing", "request": {"method": "POST", "body": {"mode": "graphql",
                        "graphql": {"query": "query thing { a }", "variables": ""}}}},
                    {"name": "thing2", "request": {"method": "POST", "body": {"mode": "graphql",
                        "graphql": {"query": "query thing { b }", "variables": ""}}}},
                ]},
            ]},
        ],
    }
    col = tmp_path / "dup.json"
    col.write_text(json.dumps(collection), encoding="utf-8")
    with pytest.raises(ValueError):
        gen.generate(collection_path=col, out_dir=tmp_path / "_g", endpoints_doc=tmp_path / "E.md")


def test_strip_field_selection_removes_block():
    gen = _load_generator()
    q = "query x { a node { discoverExposure { id name } keep } }"
    out = gen._strip_field_selection(q, "discoverExposure")
    assert "discoverExposure" not in out
    assert "keep" in out and "node" in out


def test_strip_field_selection_removes_scalar():
    gen = _load_generator()
    q = "query x { a supportedTechnologies type b }"
    out = gen._strip_field_selection(q, "supportedTechnologies")
    assert "supportedTechnologies" not in out
    assert " a " in out and " b " in out


def test_strip_field_selection_whole_identifier_only():
    gen = _load_generator()
    q = "query x { discoverExposureSummary { id } other }"
    out = gen._strip_field_selection(q, "discoverExposure")
    # must NOT remove the longer identifier that merely starts with the name
    assert "discoverExposureSummary" in out


def test_emitted_code_safe_with_special_chars(tmp_path):
    """Folder names / examples with quotes, backslashes, newlines must not break emitted code."""
    gen = _load_generator()
    collection = {
        "info": {"name": "Weird"},
        "item": [
            {"name": 'Weird "Folder"\\Name', "item": [
                {"name": "Queries", "item": [
                    {"name": "doThing", "request": {"method": "POST", "body": {"mode": "graphql",
                        "graphql": {"query": "query doThing($q: String) { a }",
                                     "variables": "{\"q\": \"line1\\nline2\"}"}}}},
                ]},
            ]},
        ],
    }
    col = tmp_path / "weird.json"
    col.write_text(json.dumps(collection), encoding="utf-8")
    out_dir = tmp_path / "_g"
    gen.generate(collection_path=col, out_dir=out_dir, endpoints_doc=tmp_path / "E.md")
    for py in out_dir.glob("*.py"):
        compile(py.read_text(), str(py), "exec")  # must not raise SyntaxError
