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


async def test_retries_on_network_error_then_succeeds(httpx_mock):
    import httpx
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_response(json={"data": {"ok": True}})
    client = GreyMatterClient(_cfg())
    out = await client.execute("query { ok }")
    assert out == {"ok": True}
    assert len(httpx_mock.get_requests()) == 2
    await client.close()


async def test_graphql_error_joins_multiple_messages(httpx_mock):
    httpx_mock.add_response(json={"errors": [{"message": "first"}, {"message": "second"}], "data": None})
    client = GreyMatterClient(_cfg())
    with pytest.raises(GreyMatterGraphQLError) as ei:
        await client.execute("query { x }")
    msg = str(ei.value)
    assert "first" in msg and "second" in msg
    await client.close()
