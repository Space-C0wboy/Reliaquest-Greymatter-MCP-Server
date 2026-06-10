from greymatter_mcp.tools._common import coerce_json, drop_none, execute_operation


def test_drop_none_filters_only_none():
    assert drop_none({"a": 1, "b": None, "c": False, "d": ""}) == {"a": 1, "c": False, "d": ""}


def test_coerce_json_parses_object_and_array_strings():
    assert coerce_json('{"severity": ["HIGH"]}') == {"severity": ["HIGH"]}
    assert coerce_json('["a", "b"]') == ["a", "b"]
    assert coerce_json('  {"a": 1}  ') == {"a": 1}  # leading whitespace tolerated


def test_coerce_json_leaves_scalars_and_non_json_untouched():
    assert coerce_json("T18w") == "T18w"          # cursor string
    assert coerce_json("incident-123") == "incident-123"  # id string
    assert coerce_json("{not valid json") == "{not valid json"  # unparseable -> kept
    assert coerce_json('"just a string"') == '"just a string"'  # parses to str -> kept as-is
    assert coerce_json(5) == 5
    assert coerce_json({"already": "object"}) == {"already": "object"}


async def test_execute_operation_coerces_json_string_objects(monkeypatch):
    captured = {}

    class FakeClient:
        async def execute(self, query, variables=None, *, customer_slug=None, retryable=True):
            captured["variables"] = variables
            return {}

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr("greymatter_mcp.tools._common.get_client", fake_get_client)
    await execute_operation(
        "q",
        {"incidentFilter": '{"severity": ["HIGH"]}', "after": "T18w", "first": 2},
    )
    assert captured["variables"]["incidentFilter"] == {"severity": ["HIGH"]}  # parsed to object
    assert captured["variables"]["after"] == "T18w"  # plain string untouched
    assert captured["variables"]["first"] == 2


async def test_execute_operation_uses_shared_client(monkeypatch):
    calls = {}

    class FakeClient:
        async def execute(self, query, variables=None, *, customer_slug=None, retryable=True):
            calls["query"] = query
            calls["variables"] = variables
            calls["customer_slug"] = customer_slug
            calls["retryable"] = retryable
            return {"ok": True}

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr("greymatter_mcp.tools._common.get_client", fake_get_client)
    out = await execute_operation("query { ok }", {"a": 1, "b": None}, customer_slug="opco")
    assert out == {"ok": True}
    assert calls["variables"] == {"a": 1}  # None dropped
    assert calls["customer_slug"] == "opco"
    assert calls["retryable"] is True  # a query is idempotent -> retryable
