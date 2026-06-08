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
